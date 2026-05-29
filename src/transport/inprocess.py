# transport/inprocess.py
"""
OSI Layer 4 InProcess Transporter (Memory/Address Space IPC).
مسؤولية هذا الناقل حصريًا:
- استدعاء دوال/كوروتينات محلية مباشرة بدون حزم شبكة أو عمليات فرعية
- تمرير سياق الجلسة (L5 Context) كمعامل شفاف دون تفسير أو تعديل
- تغليف الاستدعاء بآلية إعادة المحاولة (RetryEngine) عند التوفير
- إعداد تقارير تسليم دقيقة (DeliveryReport) تعكس حجم البيانات المنقولة
لا يخزن حالة جلسة، لا يعتمد على Presentation، ويعزل آلية النقل عن منطق المجال.
"""
from __future__ import annotations

import asyncio
import inspect
import logging
from typing import AsyncIterator, Awaitable, Callable, Optional

from transport.base import BaseTransporter, DeliveryReport, Direction, TransportError
from transport.context import TransportContext
from transport.retry import RetryEngine

logger = logging.getLogger(__name__)


class InProcessTransporter(BaseTransporter):
    """
    ناقل النقل داخل العملية (OSI L4 Memory IPC).
    يُستخدم للاتصال المباشر بين مكونات النظام في نفس مساحة الذاكرة
    مع الحفاظ على عقود النقل الموحدة (Context, DeliveryReport, Retry).
    """

    def __init__(
        self,
        target: Optional[Callable] = None,
        retry_engine: Optional[RetryEngine] = None,
        direction: Direction = Direction.OUTBOUND
    ):
        super().__init__(direction)
        self.target = target
        self.retry_engine = retry_engine
        self._inbound_handler: Optional[Callable[[bytes, TransportContext], Awaitable[bytes]]] = None

    # ── L4 Core Dispatch Logic ────────────────────────────────

    async def _execute_target(self, payload: bytes, context: TransportContext) -> bytes:
        """يُنفذ الهدف المحلي (دالة/كوروتين) مع تمرير السياق شفافًا."""
        if not self.target:
            raise TransportError(
                type(self).__name__,
                "InProcessTransporter requires a 'target' callable for OUTBOUND direction",
                status_code=500
            )
        
        # دعم الدوال التزامنية وغير التزامنية
        result = self.target(payload, context)
        if inspect.isawaitable(result):
            return await result
        return result

    async def _do_send(self, payload: bytes, context: TransportContext) -> DeliveryReport:
        """المنطق الأساسي للإرسال الموحد داخل الذاكرة."""
        try:
            response = await self._execute_target(payload, context)
            if not isinstance(response, bytes):
                raise TransportError(
                    type(self).__name__,
                    f"InProcess target returned non-bytes: {type(response).__name__}",
                    status_code=500
                )
                
            return DeliveryReport(
                success=True,
                context=context,
                bytes_sent=len(payload),
                bytes_received=len(response),
                final_offset=context.stream_offset + len(response)
            )
        except TransportError:
            raise
        except Exception as e:
            raise TransportError(
                type(self).__name__,
                f"InProcess target execution failed: {e}",
                status_code=500
            )

    async def _do_stream(self, payload: bytes, context: TransportContext) -> AsyncIterator[bytes]:
        """المنطق الأساسي للبث المتدفق داخل الذاكرة."""
        if not self.target:
            raise TransportError(
                type(self).__name__,
                "InProcessTransporter requires an async generator target for streaming",
                status_code=500
            )
            
        # توقع أن الهدف يعيد AsyncIterator[bytes]
        iterator = self.target(payload, context)
        if not hasattr(iterator, "__aiter__"):
            raise TransportError(
                type(self).__name__,
                "InProcess streaming target must return an async iterator",
                status_code=500
            )
            
        offset = context.stream_offset
        async for chunk in iterator:
            if not isinstance(chunk, bytes):
                raise TransportError(
                    type(self).__name__,
                    "Stream chunk must be bytes",
                    status_code=500
                )
            yield chunk
            offset += len(chunk)

    # ── Public L4 Contract ────────────────────────────────────

    async def send(self, payload: bytes, context: TransportContext) -> DeliveryReport:
        if self.retry_engine:
            return await self.retry_engine.execute_with_retry(
                lambda: self._do_send(payload, context), context
            )
        return await self._do_send(payload, context)

    async def stream(
        self, payload: bytes, context: TransportContext
    ) -> AsyncIterator[bytes]:
        if self.retry_engine:
            async for chunk in self.retry_engine.stream_with_retry(
                lambda: self._do_stream(payload, context), context
            ):
                yield chunk
        else:
            async for chunk in self._do_stream(payload, context):
                yield chunk

    async def serve(
        self, handler: Callable[[bytes, TransportContext], Awaitable[bytes]]
    ) -> None:
        """
        يُسجل معالجًا واردًا (Inbound) للاستدعاء المباشر داخل العملية.
        في سياق InProcess، لا يوجد "استماع للشبكة"، بل تمرير مباشر للمهام.
        يمكن استدعاؤها لتهيئة مسار INBOUND أو لربط Dispatcher مركزي.
        """
        if self.direction != Direction.INBOUND:
            raise TransportError(
                type(self).__name__,
                "serve() is only valid for INBOUND direction",
                status_code=400
            )
        self._inbound_handler = handler
        logger.debug("InProcess inbound handler registered")

    async def dispatch(self, payload: bytes, context: TransportContext) -> bytes:
        """
        نقطة دخول مباشرة للمسار الوارد (INBOUND).
        تُستخدم داخليًا أو من قبل Orchestrator لتوجيه الطلبات للمعالج المسجل.
        """
        if not self._inbound_handler:
            raise TransportError(
                type(self).__name__,
                "No inbound handler registered. Call serve() first.",
                status_code=404
            )
        return await self._inbound_handler(payload, context)

    async def close(self) -> None:
        """تنظيف مرجعي (InProcess لا يملك موارد نظام تحتاج إغلاق صريح)."""
        self.target = None
        self._inbound_handler = None
        logger.debug("InProcess transporter resources cleared")

    async def __aenter__(self) -> InProcessTransporter:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()