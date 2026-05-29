# transport/websocket.py
"""
OSI Layer 4 WebSocket Transporter (Full-Duplex Network IPC).
مسؤوليته حصريًا:
- إدارة قناة WebSocket ثنائية الاتجاه المتزامنة
- استخدام WSFramingEngine لتغليف/فك تغليف البيانات
- دمج WSKeepAlivePolicy لمراقبة صحة الاتصال
- تسليم الحمولة (bytes) عبر إطارات WS مع إعداد DeliveryReport دقيق
لا يخزن حالة جلسة، لا يفسر محتوى الحمولة، ويعزل آلية النقل عن L7.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from typing import AsyncIterator, Callable, Awaitable, Optional, Tuple

from transport.base import BaseTransporter, DeliveryReport, Direction, ErrorType, TransportError
from transport.context import TransportContext
from transport.retry import RetryEngine
from transport._ws_framing import WSFramingEngine, OP_TEXT, OP_BINARY, OP_PONG, OP_CLOSE
from transport._ws_keepalive import WSKeepAlivePolicy

logger = logging.getLogger(__name__)

class WebSocketTransporter(BaseTransporter):
    """
    ...
    Contract:
    - Raises TransportError(ErrorType.PERMANENT) on protocol-level closures (OP_CLOSE).
    - Raises TransportError(ErrorType.TRANSIENT) on network/timeout issues.
    - close() is idempotent and safe to call multiple times.
    """
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 0,
        path: str = "/",
        retry_engine: Optional[RetryEngine] = None,
        timeout: float = 30.0,
        ping_interval: float = 30.0,
        pong_timeout: float = 10.0,
        direction: Direction = Direction.OUTBOUND
    ):
        super().__init__(direction)
        self.host = host
        self.port = port
        self.path = path
        self.timeout = timeout
        self.retry_engine = retry_engine
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._server: Optional[asyncio.AbstractServer] = None
        self._handler: Optional[Callable[[bytes, TransportContext], Awaitable[bytes]]] = None
        self._keepalive = WSKeepAlivePolicy(ping_interval, pong_timeout)

    # ── Connection & Lifecycle ────────────────────────────────

    async def _ensure_connection(self) -> Tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        """يُنشئ أو يعيد استخدام اتصال TCP مُرقّى لـ WS (يفترض الترقية مُدارة خارجيًا أو مسبقًا)"""
        if not self._writer or self._writer.is_closing():
            try:
                self._reader, self._writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port), timeout=self.timeout
                )
                # ملاحظة: ترقية HTTP->WS تُترك لـ L7 أو تُفترض جاهزة هنا للحفاظ على نقاء L4
                self._keepalive.start(self._writer, on_timeout_callback=self._handle_keepalive_timeout)
                except Exception as e:
                    raise TransportError(ErrorType.TRANSIENT, f"WS connection failed: {e}") from e
                    if self._writer and self._writer.is_closing():
        # إعادة محاولة نظيفة إذا كان الـ writer في حالة إغلاق
        self._writer = self._reader = None
        return await self._ensure_connection()     
        return self._reader, self._writer

    async def _handle_keepalive_timeout(self) -> None:
        """يُستدعى عند فشل Ping/Pong المتكرر"""
        await self.close()
        logger.warning("WS Transporter closed due to keepalive timeout")

    async def _read_frame(self, reader: asyncio.StreamReader) -> Tuple[int, bytes]:
        """يقرأ إطار WS كامل من الدفق"""
        header = await asyncio.wait_for(reader.readexactly(2), timeout=self.timeout)
        fin_rsv_opcode, mask, payload_len, hdr_size = WSFramingEngine.parse_header(header)
        
        remaining = reader.readexactly(hdr_size - 2 + payload_len)
        if remaining:
            extra = await asyncio.wait_for(remaining, timeout=self.timeout)
        else:
            extra = b""
            
        mask_key = extra[:4] if mask else b""
        raw_payload = extra[4:] if mask else extra
        
        opcode = fin_rsv_opcode & 0x0F
        payload = WSFramingEngine.unmask_payload(raw_payload, mask_key)
        return opcode, payload

    # ── Core I/O Operations ───────────────────────────────────

    async def _do_send(self, payload: bytes, context: TransportContext) -> DeliveryReport:
        reader, writer = await self._ensure_connection()
        try:
            # إرسال كإطار نصي أو ثنائي حسب طبيعة الحمولة
            frame = WSFramingEngine.encode_frame(payload, opcode=OP_BINARY, mask=True)
            writer.write(frame)
            await writer.drain()
            
            # انتظار رد بسيط (افتراضي: ننتظر إطارًا واحدًا كـ ACK)
            opcode, resp_payload = await self._read_frame(reader)
            if opcode == OP_CLOSE:
                raise TransportError(ErrorType.PERMANENT, "WS peer closed connection")
                
            return DeliveryReport(
                success=True,
                context=context,
                bytes_sent=len(payload),
                bytes_received=len(resp_payload),
                final_offset=context.stream_offset + len(resp_payload)
            )
        except asyncio.TimeoutError as e:
            raise TransportError(ErrorType.TRANSIENT, f"WS read timeout: {e}")
        except Exception as e:
            raise TransportError(ErrorType.TRANSIENT, f"WS send failed: {e}")

    async def _do_stream(self, payload: bytes, context: TransportContext) -> AsyncIterator[bytes]:
        reader, writer = await self._ensure_connection()
        try:
            frame = WSFramingEngine.encode_frame(payload, opcode=OP_BINARY, mask=True)
            writer.write(frame)
            await writer.drain()
            
            offset = context.stream_offset
            while True:
                opcode, chunk = await self._read_frame(reader)
                if opcode == OP_PONG:
                    self._keepalive.handle_pong()
                    continue
                if opcode == OP_CLOSE:
                    break
                if opcode in (OP_TEXT, OP_BINARY):
                    yield chunk
                    offset += len(chunk)
        except asyncio.IncompleteReadError:
            pass
        except asyncio.TimeoutError:
            pass
        finally:
            self._keepalive.stop()

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
        if self.direction != Direction.INBOUND:
            raise TransportError(ErrorType.PERMANENT, "serve() requires INBOUND direction")
        self._handler = handler
        self._server = await asyncio.start_server(
            self._handle_client, host=self.host, port=self.port
        )
        logger.info(f"WS inbound listener started on {self.host}:{self.port}{self.path}")
        async with self._server:
            await self._server.serve_forever()

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        ctx = TransportContext(
            session_id=f"ws-{writer.get_extra_info('peername')}",
            correlation_id="auto",
            stream_offset=0
        )
        self._keepalive.start(writer, on_timeout_callback=self._handle_keepalive_timeout)
        try:
            while True:
                opcode, payload = await self._read_frame(reader)
                if opcode == OP_PING:
                    pong = WSFramingEngine.encode_frame(payload, opcode=OP_PONG, mask=False)
                    writer.write(pong)
                    await writer.drain()
                    self._keepalive.handle_pong()
                elif opcode == OP_CLOSE:
                    break
                elif opcode in (OP_TEXT, OP_BINARY) and self._handler:
                    resp = await self._handler(payload, ctx)
                    writer.write(WSFramingEngine.encode_frame(resp, opcode=OP_BINARY, mask=False))
                    await writer.drain()
        except (asyncio.IncompleteReadError, asyncio.TimeoutError):
            pass
        finally:
            self._keepalive.stop()
            with suppress(Exception):
                writer.close()
                await writer.wait_closed()

    async def close(self) -> None:
        self._keepalive.stop()
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        if self._writer and not self._writer.is_closing():
            close_frame = WSFramingEngine.encode_frame(b"", opcode=OP_CLOSE, mask=True)
            with suppress(Exception):
                self._writer.write(close_frame)
                await self._writer.drain()
                self._writer.close()
                await self._writer.wait_closed()
        self._reader = self._writer = None
        logger.debug("WS Transporter resources released")

    async def __aenter__(self) -> WebSocketTransporter:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()