# wiring/pipelines/inbound.py
"""
Inbound Communication Pipeline (Network → Application).
الأوركستريشن الوارد: بايتات خام → استخراج سياق → L6 فك ترميز → L7 تحليل بروتوكول → L5 تحديث جلسة → إرجاع للتطبيق.
مصمم للخوادم، المستقبلات، ومعالجات الأحداث الشبكية.
"""
from __future__ import annotations

import logging
from typing import Any, AsyncIterator, Dict, Optional

from transport.context import TransportContext
from session.session_dispatcher import SessionDispatcher
from presentation.pipeline import PresentationPipeline
from .base import BaseCommunicationPipeline, PipelineExecutionError

logger = logging.getLogger(__name__)


class InboundCommunicationPipeline(BaseCommunicationPipeline):
    """خط المعالجة الوارد. يدير استقبال، تحليل، وتوجيه الرسائل الواردة للتطبيق."""

    async def receive(
        self,
        raw_bytes: bytes,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
        channel_ref: Optional[str] = None
    ) -> Any:
        """يستقبل بيانات شبكية خام، يحللها بروتوكوليًا، ويعيد كائنًا تطبيقيًا جاهزًا."""
        ctx = await self._build_context(session_id, metadata=metadata or {})
        if channel_ref:
            ctx.metadata["channel_ref"] = channel_ref

        async def _core_execution():
            # 1. L5: استجلاب/إنشاء جلسة وربطها بالقناة
            channel = await self.dispatcher.route_session(ctx.session_id)
            if not channel:
                raise PipelineExecutionError("Dispatcher", f"Inbound route failed for '{ctx.session_id}'")

            # 2. L6: فك الترميز والضغط
            try:
                app_obj = self.presentation.decode(raw_bytes, target_type=Any)
            except Exception as e:
                raise PipelineExecutionError("L6-Decode", f"Malformed inbound payload: {e}", original=e)

            # 3. L7: تحليل دلالة البروتوكول (Headers, Method, Protocol Errors)
            result = await self.protocol_handler.process_inbound(app_obj, ctx)

            # 4. L5: تحديث نشاط الجلسة ونقطة التفتيش
            await self.dispatcher.touch(ctx.session_id)
            
            return result

        return await self._wrap_execution("Inbound", _core_execution())

    async def receive_stream(
        self,
        byte_stream: AsyncIterator[bytes],
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None
    ) -> AsyncIterator[Any]:
        """يستقبل تدفقًا شبكيًا مستمرًا (SSE/Chunks) ويعيد تدفق كائنات تطبيقية."""
        ctx = await self._build_context(session_id, metadata=metadata or {})
        await self.dispatcher.route_session(ctx.session_id)

        async def _stream_generator():
            async for chunk in self.presentation.decode_stream(byte_stream):
                try:
                    # L7: معالجة كل شريحة دلاليًا
                    processed = await self.protocol_handler.process_inbound(chunk, ctx)
                    await self.dispatcher.touch(ctx.session_id)
                    yield processed
                except Exception as e:
                    logger.error(f"Inbound stream processing error: {e}")
                    yield {"error": str(e), "type": "inbound_stream_error"}

        return _stream_generator()

    async def finalize(self, session_id: str, reason: str = "completed") -> None:
        """يُنهي الجلسة الواردة، يحفظ نقطة التفتيش، ويحرر القناة."""
        await self.dispatcher.release_session(session_id)
        logger.debug(f"Inbound session '{session_id}' finalized ({reason})")