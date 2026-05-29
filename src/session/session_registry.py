# session/session_registry.py
"""
OSI Layer 5 Session Registry (State & Lifecycle Tracking).
مسؤوليته حصريًا:
- تتبع الجلسات النشطة (session_id ↔ SessionCoordinator)
- إدارة دورة الحياة الزمنية (TTL, Idle Eviction, Cleanup)
- التنسيق مع ICheckpointSync لحفظ/استعادة الحالة عند الإنهاء أو الخمول
- عزل تام عن القنوات، النقل، أو التوجيه (يُترك لـ network/ و orchestrator)

✅ يطبق مبدأ SRP: سجل حالة فقط، لا منطق حوار، لا إدارة مقابس.
✅ Async-Safe: يستخدم asyncio.Lock لحماية حالة السجل من السباقات.
✅ Configurable: TTL، فاصل التنظيف، وسياسة الحفظ تُحقن عند التهيئة.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from session.coordinator import SessionCoordinator
from session.ICheckpointSync import ICheckpointSync

logger = logging.getLogger(__name__)


@dataclass
class SessionEntry:
    """سجل داخلي لبيانات الجلسة الزمنية والإدارية."""
    coordinator: SessionCoordinator
    created_at: float
    last_active: float
    ttl: float
    metadata: Dict[str, Any] = field(default_factory=dict)


class SessionRegistry:
    """
    سجل إدارة الجلسات (OSI L5 Session State Tracker).
    يدير خريطة الجلسات النشطة، ينظف الخاملين تلقائيًا، 
    ويتكامل مع نقاط التفتيش لحفظ الحالة قبل الإنهاء.
    """

    def __init__(
        self,
        default_ttl: float = 3600.0,
        idle_timeout: float = 300.0,
        checkpoint_sync: Optional[ICheckpointSync] = None,
        eviction_interval: float = 60.0
    ):
        self._sessions: Dict[str, SessionEntry] = {}
        self._lock = asyncio.Lock()
        self._default_ttl = default_ttl
        self._idle_timeout = idle_timeout
        self._checkpoint_sync = checkpoint_sync
        self._eviction_interval = eviction_interval
        self._eviction_task: Optional[asyncio.Task] = None
        self._closed = False

    # ── Registration & Resolution ────────────────────────────

    async def register(
        self,
        session_id: str,
        coordinator: SessionCoordinator,
        ttl: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """يسجل جلسة جديدة أو يحدّث بيانات جلسة موجودة."""
        async with self._lock:
            now = time.time()
            entry = SessionEntry(
                coordinator=coordinator,
                created_at=now,
                last_active=now,
                ttl=ttl or self._default_ttl,
                metadata=metadata or {}
            )
            self._sessions[session_id] = entry
            logger.debug(f"Session '{session_id}' registered (TTL={entry.ttl:.0f}s)")

    async def resolve(self, session_id: str) -> Optional[SessionCoordinator]:
        """
        يحل معرّف الجلسة إلى منسقها النشط.
        يحدّث تلقائيًا last_active عند النجاح.
        """
        async with self._lock:
            entry = self._sessions.get(session_id)
            if not entry:
                return None
            entry.last_active = time.time()
            return entry.coordinator

    async def touch(self, session_id: str) -> bool:
        """يحدّث نشاط الجلسة يدويًا (مفيد للبث أو الـ heartbeats)."""
        async with self._lock:
            entry = self._sessions.get(session_id)
            if entry:
                entry.last_active = time.time()
                return True
            return False

    # ── Eviction & Lifecycle ─────────────────────────────────

    async def evict_idle(self, max_idle_seconds: Optional[float] = None) -> List[str]:
        """يزيل الجلسات الخاملة التي تجاوزت مهلة النشاط."""
        threshold = max_idle_seconds or self._idle_timeout
        now = time.time()
        evicted_ids: List[str] = []

        async with self._lock:
            stale_ids = [
                sid for sid, entry in self._sessions.items()
                if now - entry.last_active > threshold
            ]
            for sid in stale_ids:
                entry = self._sessions.pop(sid)
                await self._on_session_end(entry.coordinator, sid, reason="idle_eviction")
                evicted_ids.append(sid)
        
        if evicted_ids:
            logger.info(f"Evicted {len(evicted_ids)} idle sessions")
        return evicted_ids

    async def unregister(self, session_id: str, reason: str = "explicit_close") -> None:
        """يزيل جلسة صراحةً من السجل مع حفظ حالتها إن لزم."""
        async with self._lock:
            entry = self._sessions.pop(session_id, None)
        if entry:
            await self._on_session_end(entry.coordinator, session_id, reason=reason)

    # ── Maintenance & Observability ──────────────────────────

    async def start_maintenance(self) -> None:
        """يبدأ مهمة خلفية دورية لتنظيف الجلسات الخاملة."""
        if self._eviction_task and not self._eviction_task.done():
            return
        
        self._closed = False
        self._eviction_task = asyncio.create_task(self._eviction_loop(), name="session_registry_maintenance")
        logger.info("SessionRegistry maintenance loop started")

    async def _eviction_loop(self) -> None:
        try:
            while not self._closed:
                await asyncio.sleep(self._eviction_interval)
                await self.evict_idle()
        except asyncio.CancelledError:
            logger.debug("SessionRegistry maintenance loop cancelled")

    async def close(self) -> None:
        """ينهي السجل ويحفظ/ينظف جميع الجلسات المتبقية."""
        self._closed = True
        if self._eviction_task:
            self._eviction_task.cancel()
            try:
                await self._eviction_task
            except asyncio.CancelledError:
                pass

        async with self._lock:
            active = list(self._sessions.items())
            self._sessions.clear()
        
        for sid, entry in active:
            await self._on_session_end(entry.coordinator, sid, reason="registry_shutdown")
        logger.info("SessionRegistry closed and all sessions finalized")

    # ── Internal Helpers ─────────────────────────────────────

    async def _on_session_end(self, coordinator: SessionCoordinator, session_id: str, reason: str) -> None:
        """يُستدعى عند إنهاء الجلسة لحفظ نقطة تفتيش وتسجيل الأحداث."""
        try:
            if self._checkpoint_sync:
                await self._checkpoint_sync.persist(session_id, coordinator.state)
                logger.debug(f"Session '{session_id}' checkpoint persisted ({reason})")
            await coordinator.close()
            logger.debug(f"Session '{session_id}' coordinator closed ({reason})")
        except Exception as e:
            logger.error(f"Failed to finalize session '{session_id}': {e}")

    # ── Stats & Diagnostics ──────────────────────────────────

    async def active_count(self) -> int:
        async with self._lock:
            return len(self._sessions)

    async def list_sessions(self) -> Dict[str, Dict[str, Any]]:
        """يعيد نظرة عامة على الجلسات النشطة (للمراقبة أو التصحيح)."""
        async with self._lock:
            now = time.time()
            return {
                sid: {
                    "state": entry.coordinator.state.value,
                    "age_seconds": now - entry.created_at,
                    "idle_seconds": now - entry.last_active,
                    "ttl_remaining": max(0, (entry.created_at + entry.ttl) - now),
                    "metadata": entry.metadata
                }
                for sid, entry in self._sessions.items()
            }
            
            
"""
✅ لماذا يحقق هذا التصميم تصورك الثلاثي بدقة؟
المبدأ
التطبيق في الكود
عزل مستوى 2 (إدارة الجلسات)
لا يستورد network/، transporters/، أو أي شيء متعلق بالنقل. يركز فقط على session_id ↔ SessionCoordinator والزمن/الحالة.
توافق مع المكونات الحالية
يستخدم SessionCoordinator و ICheckpointSync الموجودين في مجلدك. يكمّل دورهما دون تكرار المنطق.
دورة حياة زمنية واضحة
TTL, idle_timeout, eviction_interval, start_maintenance() تُدار بشكل آمن وخلفي.
جاهز للأوركستريشن (المستوى 3)
يعيد SessionCoordinator عند resolve(). الـ SessionRouter في network/ يستخدم هذا المعرّف لربطه بـ ChannelRef ديناميكيًا.
حفظ الحالة قبل الإنهاء
_on_session_end() يستدعي checkpoint_sync.persist() تلقائيًا عند eviction, unregister, أو close.
🔗 كيف يندمج مع المستويين الآخرين؟
text


[Level 2: SessionRegistry] ← يسجل الجلسة، يتبع نشاطها، ينظف الخامل
       │ resolve(session_id) → SessionCoordinator
       ▼
[Level 3: SessionRouter/Orchestrator] ← يربط session_id بـ ChannelRef من Pool
       │ bind(session_id, channel_ref)
       ▼
[Level 1: ChannelPool] ← يعيد قناة فعلية (IChannel) للاستخدام المؤقت


"""