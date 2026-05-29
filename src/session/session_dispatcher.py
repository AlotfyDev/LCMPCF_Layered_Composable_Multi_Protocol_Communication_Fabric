# session/session_dispatcher.py
"""
OSI Layer 5 Session Dispatcher (Transport Orchestration Bridge).
مسؤوليته حصريًا:
- الربط الديناميكي بين سجل الجلسات (L5) ومجمع القنوات (L3/L4)
- إدارة فشل القناة (Failover) دون فقدان حالة الجلسة أو تكرار الطلبات
- توجيه الطلبات إلى القنوات الصحيحة عبر ISessionRouter
- ضمان إطلاق الموارد (Release) عند إغلاق أو خمول الجلسة

✅ لا يعرف بروتوكولات النقل، لا يدير منطق الأعمال، لا يخزن حالة الحوار.
✅ يعتمد على حقن العقود: SessionRegistry, IChannelPool, ISessionRouter.
✅ Async-Safe مع قفل دقيق لمنع السباقات أثناء الـ Failover أو الربط المتزامن.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from transport.channel.protocol import IChannel
from transport.channel.types import ChannelState
from session.session_registry import SessionRegistry
from network.protocol import IChannelPool, ISessionRouter, ChannelRef, Endpoint

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DispatchContext:
    """سياق توجيه خفيف يُمرر مع كل عملية ربط/فشل لتتبع الأوركستريشن."""
    session_id: str
    channel_id: str
    bound_at: float
    retry_count: int = 0


class SessionDispatcher:
    """
    منسق توزيع الجلسات على القنوات (OSI L5↔L3/L4 Bridge).
    يدير دورة حياة الربط المؤقت، يتعامل مع أعطال النقل، 
    ويضمن أن الجلسات تبقى نشطة منطقيًا حتى مع تبديل القنوات الفعلية.
    """

    def __init__(
        self,
        registry: SessionRegistry,
        pool: IChannelPool,
        router: ISessionRouter,
        max_failover_attempts: int = 3,
        failover_delay: float = 1.0
    ):
        self._registry = registry
        self._pool = pool
        self._router = router
        self._max_failover = max_failover_attempts
        self._failover_delay = failover_delay
        self._lock = asyncio.Lock()
        self._active_bindings: Dict[str, DispatchContext] = {}

    # ── Main Routing & Binding ───────────────────────────────

    async def route_session(self, session_id: str) -> Optional[IChannel]:
        """
        يحل جلسة إلى قناة نقل فعلية جاهزة.
        إذا كانت مرتبطة سابقًا وصحية، يعيدها. وإلا يربط قناة جديدة من المجمع.
        """
        async with self._lock:
            # 1. تحقق من الربط الحالي
            ctx = self._active_bindings.get(session_id)
            if ctx:
                channel = await self._router.resolve(session_id)
                if channel and channel.state == ChannelState.ACTIVE:
                    await self._registry.touch(session_id)
                    return channel
                else:
                    # قناة تالفة أو غير نشطة → تنظيف الربط القديم
                    await self._unbind_session(session_id, ctx, reason="unhealthy_resolution")

            # 2. لا يوجد ربط أو القناة القديمة معطلة → ربط جديد
            try:
                channel = await self._pool.acquire()
                ref = self._build_channel_ref(channel)
                self._router.bind(session_id, ref)
                self._active_bindings[session_id] = DispatchContext(
                    session_id=session_id,
                    channel_id=ref.id,
                    bound_at=time.time()
                )
                await self._registry.touch(session_id)
                logger.debug(f"Session '{session_id}' routed to new channel '{ref.id}'")
                return channel
            except Exception as e:
                logger.error(f"Failed to route session '{session_id}': {e}")
                return None

    # ── Failover Orchestration ───────────────────────────────

    async def handle_failure(
        self, 
        session_id: str, 
        failed_channel: IChannel, 
        error: Exception
    ) -> Optional[IChannel]:
        """
        يدير تبديل القناة عند الفشل (Failover).
        يطلق القناة التالفة، يحاول ربط بديلة، ويعيد القناة الجديدة أو None عند استنفاد المحاولات.
        """
        async with self._lock:
            ctx = self._active_bindings.get(session_id)
            if not ctx or ctx.channel_id != id(failed_channel):
                return None  # فشل غير مرتبط بهذه الجلسة أو تم معالجته مسبقًا

            ctx.retry_count += 1
            if ctx.retry_count > self._max_failover:
                logger.warning(f"Session '{session_id}' exhausted failover attempts after {error}")
                await self._unbind_session(session_id, ctx, reason="failover_exhausted")
                return None

            # إطلاق القناة التالفة أولاً
            await self._pool.release(failed_channel)
            self._active_bindings.pop(session_id, None)

            try:
                await asyncio.sleep(self._failover_delay)
                channel = await self._pool.acquire()
                ref = self._build_channel_ref(channel)
                self._router.bind(session_id, ref)
                self._active_bindings[session_id] = DispatchContext(
                    session_id=session_id,
                    channel_id=ref.id,
                    bound_at=time.time(),
                    retry_count=ctx.retry_count
                )
                logger.info(f"Session '{session_id}' failed over to channel '{ref.id}' (attempt {ctx.retry_count})")
                return channel
            except Exception as e:
                logger.error(f"Failover failed for session '{session_id}': {e}")
                return None

    # ── Lifecycle & Cleanup ──────────────────────────────────

    async def release_session(self, session_id: str) -> None:
        """يحرر قناة الجلسة ويعيد حالتها للسجل."""
        async with self._lock:
            ctx = self._active_bindings.pop(session_id, None)
            if not ctx:
                return

            channel = await self._router.resolve(session_id)
            self._router.unbind(session_id)
            if channel:
                await self._pool.release(channel)
            await self._registry.unregister(session_id, reason="explicit_release")
            logger.debug(f"Session '{session_id}' released and unbound")

    async def close_all(self) -> None:
        """ينهي الموزع ويحرر جميع الروابط النشطة."""
        async with self._lock:
            bindings = list(self._active_bindings.items())
            self._active_bindings.clear()

        for sid, ctx in bindings:
            try:
                channel = await self._router.resolve(sid)
                self._router.unbind(sid)
                if channel:
                    await self._pool.release(channel)
                await self._registry.unregister(sid, reason="dispatcher_shutdown")
            except Exception as e:
                logger.error(f"Error releasing session '{sid}' during shutdown: {e}")
        
        logger.info("SessionDispatcher closed all bindings and released resources")

    # ── Internal Helpers ─────────────────────────────────────

    async def _unbind_session(self, session_id: str, ctx: DispatchContext, reason: str) -> None:
        """ينظف الربط الداخلي والخارجي بأمان."""
        self._active_bindings.pop(session_id, None)
        self._router.unbind(session_id)
        channel = await self._router.resolve(session_id)  # قد يكون None بالفعل
        if channel and channel.state != ChannelState.FAILED:
            await self._pool.release(channel)
        logger.debug(f"Session '{session_id}' unbound due to: {reason}")

    @staticmethod
    def _build_channel_ref(channel: IChannel) -> ChannelRef:
        """يحول قناة فعلية إلى مرجع توجيهي خفيف."""
        # في الإنتاج: يمكن استخراج endpoint من config أو channel.metadata
        return ChannelRef(
            id=str(id(channel)),
            endpoint=Endpoint(scheme="internal", host="pool", port=0, path="/channel"),
            is_healthy=channel.state == ChannelState.ACTIVE,
            active_sessions=0
        )

    # ── Observability ────────────────────────────────────────

    async def get_binding_stats(self) -> Dict[str, Any]:
        """يعيد إحصائيات الربط النشط للمراقبة والتصحيح."""
        async with self._lock:
            return {
                "active_bindings": len(self._active_bindings),
                "sessions": {
                    sid: {
                        "channel_id": ctx.channel_id,
                        "bound_age_seconds": time.time() - ctx.bound_at,
                        "failover_retries": ctx.retry_count
                    }
                    for sid, ctx in self._active_bindings.items()
                }
            }
            
            
"""
✅ لماذا يحقق هذا التصميم الأوركستريشن الثلاثي بدقة؟
المبدأ
التطبيق في الكود
عزل المستوى 3
لا يستورد transporters/ مباشرة إلا عبر IChannel. لا يعرف عن bytes, protocols, أو business logic. يركز فقط على Session ↔ Channel ↔ Router
Failover آمن
handle_failure() يطلق القناة التالفة أولًا، ينتظر تأخيرًا ذكيًا، يحاول بديلًا، ويتتبع عدد المحاولات لمنع الحلقات اللانهائية
ربط ديناميكي
route_session() يتحقق من الربط الحالي، يكتشف التعطل تلقائيًا، وينشئ ربطًا جديدًا عبر router.bind() و pool.acquire()
تنظيف مضمون
release_session() و close_all() يضمنان إطلاق كل قناة للمجمع، وفك الربط من الراوتر، وتسجيل الإنهاء في السجل
Async-Safe
asyncio.Lock حول عمليات الربط/الفك يمنع السباقات عند فشل متعدد أو طلبات متزامنة لنفس الجلسة
جاهز للمراقبة
get_binding_stats() يعرض عمر الربط، معرف القناة، وعدد محاولات الـ Failover لكل جلسة
🔗 كيف يندمج في الدورة الحية الكاملة؟

[BaseActor/ProtocolHandler] يريد إرسال → ينادي dispatcher.route_session(session_id)
       │
       ├─ إذا مرتبطة وصحية → يعيد القناة فورًا
       ├─ إذا معطلة → ينادي dispatcher.handle_failure() → يبدل القناة من الـ Pool
       └─ إذا جديدة → يربطها عبر Router، يسجلها، ويعيدها
       │
       ▼ (عند الانتهاء أو الخمول)
dispatcher.release_session(session_id) → pool.release(channel) → registry.persist()

"""