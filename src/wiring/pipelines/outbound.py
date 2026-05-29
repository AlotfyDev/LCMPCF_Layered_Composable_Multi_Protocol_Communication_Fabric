# wiring/pipelines/outbound.py
"""
Outbound Communication Pipeline (Application → Network).
الأوركستريشن الصادر: سياق → ترميز L6 → توجيه جلسة L5 → إرسال L4 → فك ترميز L6 → إرجاع.
يدعم البث المتدفق (Streaming) والعزل الطبقي الصارم.
"""
from __future__ import annotations

import logging
from typing import Any, AsyncIterator, Optional

from transport.context import TransportContext
from transport.channel.protocol import IChannel
from session.session_dispatcher import SessionDispatcher
from presentation.pipeline import PresentationPipeline
from .base import BaseCommunicationPipeline, PipelineExecutionError

logger = logging.getLogger(__name__)


class OutboundCommunicationPipeline(BaseCommunicationPipeline):
    """خط المعالجة الصادر. يدير دورة حياة الإرسال الكامل مع ضمانات التسليم."""

    async def send(
        self,
        payload: Any,
        session_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        stream: bool = False,
        metadata: Optional[dict[str, Any]] = None
    ) -> Any:
        """يُرسل حمولة تطبيقية عبر الشبكة مع إدارة جلسات وقنوات ديناميكية."""
        ctx = await self._build_context(session_id, correlation_id, metadata)
        
        async def _core_execution():
            # 1. L7: تحضير دلالي (هيدرز، تنسيق بروتوكول، تحقق مبدئي)
            prepared = await self.protocol_handler.prepare_outbound(payload, ctx)
            
            # 2. L6: ترميز سلكي (Serialize + Compress)
            wire_bytes = self.presentation.encode(prepared)
            
            # 3. L5/L3: توجيه الجلسة إلى قناة صحية
            channel = await self.dispatcher.route_session(ctx.session_id)
            if not channel:
                raise PipelineExecutionError("Dispatcher", f"Failed to route session '{ctx.session_id}'")

            try:
                if stream:
                    return await self._stream_send(channel, wire_bytes, ctx)
                else:
                    return await self._sync_send(channel, wire_bytes, ctx)
            except Exception as e:
                await self.dispatcher.handle_failure(ctx.session_id, channel, e)
                raise

        return await self._wrap_execution("Outbound", _core_execution())

    async def _sync_send(self, channel: IChannel, wire_bytes: bytes, ctx: TransportContext) -> Any:
        """إرسال متزامن كامل (Request/Response)."""
        report = await channel.send(wire_bytes, ctx)
        if not report.success:
            raise PipelineExecutionError("L4", f"Delivery failed: {report.error}")

        # L6: فك ترميز الرد
        try:
            decoded = self.presentation.decode(report.data or b"", target_type=Any)
        except Exception as e:
            raise PipelineExecutionError("L6-Decode", str(e), original=e)

        # L7: معالجة دلالية للرد (تحقق من status، تنسيق خطأ بروتوكولي)
        return await self.protocol_handler.process_outbound_response(decoded, ctx)

    async def _stream_send(self, channel: IChannel, wire_bytes: bytes, ctx: TransportContext) -> AsyncIterator[Any]:
        """إرسال متدفق (Streaming) مع عزل الأخطاء لكل شريحة."""
        async def _stream_generator():
            # يفترض أن القناة تدعم stream() أو أن L7 يدير التدفق مباشرة
            async for chunk in channel.stream(wire_bytes, ctx):
                try:
                    decoded = self.presentation.decode(chunk.data, target_type=Any)
                    yield await self.protocol_handler.process_outbound_response(decoded, ctx)
                    await self.dispatcher.touch(ctx.session_id)
                except Exception as e:
                    logger.warning(f"Stream decode error for session '{ctx.session_id}': {e}")
                    yield {"error": str(e), "type": "stream_decode"}
        
        return _stream_generator()

    async def release(self, session_id: str) -> None:
        """يحرر قناة الجلسة وينظف الموارد عند انتهاء الحوار."""
        await self.dispatcher.release_session(session_id)