# protocols/inprocess_handler.py
"""
OSI Layer 7 InProcess Application Protocol Handler.
مسؤوليته حصريًا: استدعاء دوال/كروتينات محلية مباشرة، حقن سياق الجلسة،
إدارة التزامن (sync/async)، وترجمة الاستثناءات إلى صيغ بروتوكولية موحدة.

✅ يتجاوز التسلسل/الضغط تلقائيًا (Identity Transform) وفق قاعدة OSI L6 للذاكرة المشتركة.
✅ يفوض النقل الفعلي لـ Channel (إن وُجد) أو يستدعي الهدف مباشرة (Zero-Copy).
✅ يدعم البث المتدفق (AsyncGenerators) والاستدعاء المباشر الموحد.
"""
from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Any, AsyncIterator, Awaitable, Callable, Optional

from transport.base import TransportError
from transport.context import TransportContext
from presentation.pipeline import PresentationPipeline
from protocols.error_mapper import ProtocolErrorMapper, ProtocolType

logger = logging.getLogger(__name__)


class InProcessProtocolHandler:
    """
    معالج بروتوكول الذاكرة المشتركة (OSI L7 Local IPC Protocol).
    يدير دلالة الاستدعاء المحلي، حقن السياق، وتحويل الأخطاء التطبيقية إلى استجابات بروتوكولية.
    """

    def __init__(
        self,
        target: Optional[Callable] = None,
        pipeline: Optional[PresentationPipeline] = None,
        auto_context_injection: bool = True
    ):
        self.target = target
        self.pipeline = pipeline
        self.auto_context_injection = auto_context_injection

    # ── Unified Invocation (Request/Response) ─────────────────

    async def invoke(
        self,
        payload: Any = None,
        context: Optional[TransportContext] = None,
        target_override: Optional[Callable] = None
    ) -> Any:
        """
        ينفذ استدعاءً مباشرًا داخل الذاكرة مع إدارة بروتوكول L7 كاملة.
        يتجاوز الترميز/الضغط تلقائيًا ما لم يُطلب صراحةً عبر metadata.
        """
        ctx = context or TransportContext(session_id="inproc-auto", correlation_id="auto")
        target = target_override or self.target
        if not target:
            raise ValueError("No target callable provided for in-process execution")

        try:
            # L6 Bypass Logic: تفكيك صريح فقط عند الطلب
            if self.pipeline and ctx.metadata.get("l6_decode_required"):
                payload = self.pipeline.decode(payload, target_type=Any)

            args, kwargs = self._build_call_args(payload, ctx)
            result = await self._execute_safely(target, args, kwargs)

            # L6 Bypass Logic: ترميز صريح فقط عند الطلب
            if self.pipeline and ctx.metadata.get("l6_encode_required"):
                result = self.pipeline.encode(result)

            return result
        except TransportError:
            raise
        except Exception as e:
            err_resp = ProtocolErrorMapper.map(e, protocol=ProtocolType.INPROCESS)
            raise TransportError(err_resp.protocol_status, err_resp.message) from e

    # ── Streaming Invocation (AsyncGenerators) ────────────────

    async def invoke_stream(
        self,
        payload: Any = None,
        context: Optional[TransportContext] = None,
        target_override: Optional[Callable] = None
    ) -> AsyncIterator[Any]:
        """يدعم استدعاء مولّدات غير متزامنة للبث داخل الذاكرة (Zero-Copy Streaming)."""
        ctx = context or TransportContext(session_id="inproc-stream", correlation_id="auto")
        target = target_override or self.target
        if not target:
            raise ValueError("No stream target provided")

        if self.pipeline and ctx.metadata.get("l6_decode_required"):
            payload = self.pipeline.decode(payload, target_type=Any)

        args, kwargs = self._build_call_args(payload, ctx)
        gen = target(*args, **kwargs)

        # دعم المولّدات التزامنية وغير التزامنية
        if hasattr(gen, "__aiter__"):
            async for item in gen:
                yield self._maybe_encode(item, ctx)
        elif inspect.isgenerator(gen):
            for item in gen:
                yield self._maybe_encode(item, ctx)
        else:
            # دالة عادية تعيد قيمة واحدة
            yield self._maybe_encode(gen, ctx)

    # ── Registration / Inbound Routing ────────────────────────

    async def serve(self, handler: Callable[[Any, TransportContext], Awaitable[Any]]) -> None:
        """
        في سياق InProcess، serve() يسجل المعالج كهدف افتراضي.
        لا يوجد استماع للشبكة، فقط تعيين مرجعي (Reference Binding).
        """
        self.target = handler
        logger.debug("InProcess protocol handler target registered")

    # ── Internal Helpers ──────────────────────────────────────

    def _build_call_args(self, payload: Any, ctx: TransportContext):
        """يجهز معاملات الاستدعاء مع حقن السياق تلقائيًا عند التمكين."""
        if self.auto_context_injection:
            return (), {"payload": payload, "context": ctx}
        return (payload,), {}

    async def _execute_safely(self, target: Callable, args: tuple, kwargs: dict) -> Any:
        """ينفذ الهدف مع كشف تلقائي للتزامن (Sync/Async)."""
        res = target(*args, **kwargs)
        if inspect.isawaitable(res):
            return await res
        return res

    def _maybe_encode(self, item: Any, ctx: TransportContext) -> Any:
        """يشفّر العنصر فقط إذا طُلب صراحةً (يحمي أداء الذاكرة المشتركة)."""
        if self.pipeline and ctx.metadata.get("l6_encode_required"):
            return self.pipeline.encode(item)
        return item
        
        
        
"""

✅ لماذا هذا التصميم يحقق المطلوب معماريًا؟
المعيار
التطبيق في الكود
OSI L6 Bypass Rule
يتجاوز Pipeline.encode/decode افتراضيًا. يستخدم metadata["l6_*_required"] كـ Flag صريح عند الحاجة فقط. يحمي أداء الذاكرة المشتركة من overhead غير ضروري.
Zero-Copy Invocation
يمرر الكائنات (dict, BaseModel, إلخ) كما هي بين BaseActor والهدف. لا تحويلات JSON/Bytes إلا عند الطلب الصريح.
Sync/Async Unification
inspect.isawaitable() و hasattr(gen, "__aiter__") يضمنان دعمًا شفافًا للدوال التقليدية والكوروتينات والمولّدات.
Error Translation
يلتف أي استثناء بايثون عبر ProtocolErrorMapper.map(..., ProtocolType.INPROCESS) ليعيد TransportError متوافق مع L5/L7 دون تسرب تفاصيل التنفيذ.
Clean L7 Boundary
لا يعرف شيئًا عن httpx, subprocess, أو socket. يركز فقط على دلالة الاستدعاء المحلي، حقن السياق، وتوحيد الأخطاء.
No Channel Dependency
الذاكرة المشتركة لا تحتاج إدارة اتصال شبكي. إذا طلب ActorAssembler توحيد الواجهة، يمكن تغليفه بـ IdentityChannel لاحقًا دون لمس هذا الملف.
🔄 كيف يختلف عن المعالجات الشبكية؟
البعد
HTTP/CLI/WS Handlers
InProcess Handler
النقل
يعتمد على Channel (TCP/WS/Stdio)
استدعاء مباشر (Direct Memory Call)
L6 Pipeline
مفعّل افتراضيًا (لأن البيانات تعبر السلك)
معطل افتراضيًا (Zero-Copy)، يُفعّل بالـ Metadata فقط
التزامن
asyncio.run_in_executor أو httpx.stream
inspect.isawaitable + كشف المولّدات مباشرة
دورة الحياة
open() → active → close()
عديمة الحالة (Stateless Invocation)

"""