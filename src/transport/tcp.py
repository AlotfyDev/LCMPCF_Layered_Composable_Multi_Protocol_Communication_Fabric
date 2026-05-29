# transport/tcp.py
"""
OSI Layer 4 TCP Transporter (Network IPC).
مسؤولية هذا الناقل حصريًا:
- إدارة اتصالات TCP الموثوقة مع إطار طول ثابت (Length-Prefixed Framing)
- تسليم الحمولة (bytes) واستقبال الردود عبر مقابس الشبكات
- حقن سياق الجلسة (L5 Context) بشكل شفاف وتتبعه في تقارير التسليم
- دعم إعادة المحاولة عبر RetryEngine المُحقون من L4/L5
لا يخزن حالة جلسة، لا يفسر محتوى البيانات، ويعزل آلية النقل عن منطق المجال.
"""
from __future__ import annotations

import asyncio
import struct
import logging
from contextlib import suppress
from typing import AsyncIterator, Callable, Awaitable, Optional

from transport.base import BaseTransporter, DeliveryReport, Direction, ErrorType, TransportError
from transport.context import TransportContext
from transport.retry import RetryEngine

logger = logging.getLogger(__name__)


class TCPTransporter(BaseTransporter):
    """
    ناقل النقل عبر TCP (OSI L4 Network IPC).
    يُستخدم للاتصال بين العمليات عبر الشبكة (مثل A2A أو الخدمات الموزعة)
    مع الحفاظ على عقود النقل الموحدة والشفافية السياقية.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 0,
        retry_engine: Optional[RetryEngine] = None,
        timeout: float = 30.0,
        direction: Direction = Direction.OUTBOUND
    ):
        super().__init__(direction)
        self.host = host
        self.port = port
        self.timeout = timeout
        self.retry_engine = retry_engine
        self._server: asyncio.AbstractServer | None = None
        self._handler: Optional[Callable[[bytes, TransportContext], Awaitable[bytes]]] = None

    # ── TCP Framing & Connection Helpers ──────────────────────

    def _frame(self, data: bytes) -> bytes:
        """يُغلّف البيانات بطول ثابت (Network Byte Order) لضمان حدود الشرائح."""
        return struct.pack(">I", len(data)) + data

    async def _read_framed(self, reader: asyncio.StreamReader, timeout: float) -> bytes:
        """يقرأ طول الحزمة ثم البيانات بدقة، مع احترام المهلة الزمنية."""
        header = await asyncio.wait_for(reader.readexactly(4), timeout=timeout)
        length = struct.unpack(">I", header)[0]
        return await asyncio.wait_for(reader.readexactly(length), timeout=timeout)

    async def _ensure_connection(self, timeout: float) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        """يُنشئ اتصال TCP جديد مع التعامل مع الأخطاء الشبكية الأولية."""
        try:
            return await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), timeout=timeout
            )
        except ConnectionRefusedError as e:
            raise TransportError(ErrorType.PERMANENT, f"TCP connection refused: {e}")
        except asyncio.TimeoutError as e:
            raise TransportError(ErrorType.TRANSIENT, f"TCP connection timeout: {e}")
        except OSError as e:
            raise TransportError(ErrorType.TRANSIENT, f"TCP network error: {e}")

    # ── L4 Core I/O Operations ────────────────────────────────

    async def _do_send(self, payload: bytes, context: TransportContext) -> DeliveryReport:
        """المنطق الأساسي للإرسال الموحد عبر TCP."""
        reader, writer = None, None
        try:
            reader, writer = await self._ensure_connection(self.timeout)
            writer.write(self._frame(payload))
            await writer.drain()
            
            response = await self._read_framed(reader, self.timeout)
            return DeliveryReport(
                success=True,
                context=context,
                bytes_sent=len(payload),
                bytes_received=len(response),
                final_offset=context.stream_offset + len(response)
            )
        except asyncio.TimeoutError as e:
            raise TransportError(ErrorType.TRANSIENT, f"TCP read timeout: {e}")
        except asyncio.IncompleteReadError as e:
            raise TransportError(ErrorType.PERMANENT, f"TCP stream truncated: {e}")
        finally:
            if writer:
                with suppress(Exception):
                    writer.close()
                    await writer.wait_closed()

    async def _do_stream(self, payload: bytes, context: TransportContext) -> AsyncIterator[bytes]:
        """المنطق الأساسي للبث المتدفق عبر TCP مع دعم الحدود الذكية."""
        reader, writer = await self._ensure_connection(self.timeout)
        try:
            writer.write(self._frame(payload))
            await writer.drain()
            
            offset = context.stream_offset
            while True:
                try:
                    # مهلة قصيرة للكشف عن نهاية الدفق أو الخمول
                    chunk = await self._read_framed(reader, timeout=0.5)
                    yield chunk
                    offset += len(chunk)
                except asyncio.TimeoutError:
                    break  # انتهاء الدفق أو خمول الشبكة
                except asyncio.IncompleteReadError:
                    break  # اتصال مغلق من الطرف البعيد
        finally:
            if writer:
                with suppress(Exception):
                    writer.close()
                    await writer.wait_closed()

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
        """يُشغل مستمع TCP وارد ويوجه الطلبات للمعالج المسجل."""
        if self.direction != Direction.INBOUND:
            raise TransportError(ErrorType.PERMANENT, "serve() requires INBOUND direction")
        
        self._handler = handler
        self._server = await asyncio.start_server(
            self._handle_client, host=self.host, port=self.port
        )
        logger.info(f"TCP inbound listener started on {self.host}:{self.port}")
        async with self._server:
            await self._server.serve_forever()

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """يدير دورة حياة عميل وارد واحد."""
        # L4 شفاف: يُولّد سياقًا مبدئيًا يُملأ لاحقًا من حمولة L7 إذا لزم
        ctx = TransportContext(
            session_id=f"tcp-{writer.get_extra_info('peername')}",
            correlation_id="auto",
            stream_offset=0
        )
        try:
            while True:
                try:
                    payload = await self._read_framed(reader, self.timeout)
                except (asyncio.IncompleteReadError, asyncio.TimeoutError):
                    break
                
                if self._handler:
                    response = await self._handler(payload, ctx)
                    writer.write(self._frame(response))
                    await writer.drain()
        finally:
            with suppress(Exception):
                writer.close()
                await writer.wait_closed()

    async def close(self) -> None:
        """يُغلق الخادم الوارد ويحرر موارد المآخذ."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        logger.debug("TCP transporter resources released")

    async def __aenter__(self) -> TCPTransporter:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()