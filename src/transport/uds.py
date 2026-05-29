# transport/uds.py
"""
OSI Layer 4 UDS Transporter (Unix Domain Socket IPC).
مسؤولية هذا الناقل حصريًا:
- إدارة اتصالات UDS عالية الأداء بين العمليات على نفس الجهاز
- تسليم الحمولة (bytes) عبر مقابس محلية مع تحديد حدود الرسائل (Newline Delimited)
- حقن سياق الجلسة (L5 Context) بشكل شفاف وتتبعه في تقارير التسليم
- دعم إعادة المحاولة عبر RetryEngine المُحقون من L4/L5
لا يخزن حالة جلسة، لا يفسر محتوى البيانات، ويعزل آلية النقل عن بروتوكولات L7.
"""
from __future__ import annotations

import asyncio
import json
import os
import logging
from contextlib import suppress
from typing import AsyncIterator, Callable, Awaitable, Optional

from transport.base import BaseTransporter, DeliveryReport, Direction, ErrorType, TransportError
from transport.context import TransportContext
from transport.retry import RetryEngine

logger = logging.getLogger(__name__)


class UDSTransporter(BaseTransporter):
    """
    ناقل النقل عبر مقابس يونكس المحلية (OSI L4 UDS IPC).
    يُستخدم للاتصال السريع منخفض التأخير بين العمليات على نفس الجهاز
    مع الحفاظ على عقود النقل الموحدة والشفافية السياقية.
    """

    def __init__(
        self,
        socket_path: str,
        retry_engine: Optional[RetryEngine] = None,
        timeout: float = 30.0,
        direction: Direction = Direction.OUTBOUND
    ):
        super().__init__(direction)
        self.socket_path = socket_path
        self.timeout = timeout
        self.retry_engine = retry_engine
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._server: asyncio.AbstractServer | None = None
        self._handler: Optional[Callable[[bytes, TransportContext], Awaitable[bytes]]] = None

    # ── Connection Management ─────────────────────────────────

    async def _ensure_connection(self) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        """يُؤسس أو يعيد استخدام اتصال UDS مع التعامل مع أخطاء النظام."""
        if self._writer is None or self._writer.is_closing():
            try:
                if os.path.exists(self.socket_path):
                    self._reader, self._writer = await asyncio.wait_for(
                        asyncio.open_unix_connection(self.socket_path),
                        timeout=self.timeout
                    )
                else:
                    raise TransportError(ErrorType.PERMANENT, f"UDS socket not found: {self.socket_path}")
            except ConnectionRefusedError as e:
                raise TransportError(ErrorType.TRANSIENT, f"UDS connection refused: {e}")
            except asyncio.TimeoutError as e:
                raise TransportError(ErrorType.TRANSIENT, f"UDS connection timeout: {e}")
            except OSError as e:
                raise TransportError(ErrorType.TRANSIENT, f"UDS socket error: {e}")
        return self._reader, self._writer

    async def _cleanup_connection(self) -> None:
        """يُغلق اتصال UDS الوارد بأمان."""
        if self._writer and not self._writer.is_closing():
            with suppress(Exception):
                self._writer.close()
                await self._writer.wait_closed()
            self._writer = None
            self._reader = None

    # ── L4 Core I/O Operations ────────────────────────────────

    async def _do_send(self, payload: bytes, context: TransportContext) -> DeliveryReport:
        """المنطق الأساسي للإرسال الموحد عبر UDS مع تحديد حدود الرسائل."""
        reader, writer = await self._ensure_connection()
        try:
            # إرسال الحمولة مع محدد سطر جديد (Newline Delimited)
            writer.write(payload + b"\n")
            await writer.drain()
            
            # استقبال الرد حتى محدد السطر
            response = await asyncio.wait_for(reader.readline(), timeout=self.timeout)
            if not response:
                raise TransportError(ErrorType.PERMANENT, "UDS stream closed unexpectedly")
                
            return DeliveryReport(
                success=True,
                context=context,
                bytes_sent=len(payload),
                bytes_received=len(response),
                final_offset=context.stream_offset + len(response)
            )
        except asyncio.TimeoutError as e:
            raise TransportError(ErrorType.TRANSIENT, f"UDS read timeout: {e}")
        except asyncio.IncompleteReadError as e:
            raise TransportError(ErrorType.PERMANENT, f"UDS stream truncated: {e}")

    async def _do_stream(self, payload: bytes, context: TransportContext) -> AsyncIterator[bytes]:
        """المنطق الأساسي للبث المتدفق عبر UDS مع دعم الحدود الذكية."""
        reader, writer = await self._ensure_connection()
        try:
            writer.write(payload + b"\n")
            await writer.drain()
            
            offset = context.stream_offset
            while True:
                try:
                    chunk = await asyncio.wait_for(reader.readline(), timeout=0.5)
                    if not chunk:
                        break  # انتهاء الدفق
                    yield chunk
                    offset += len(chunk)
                except asyncio.TimeoutError:
                    break  # خمول الشبكة أو انتهاء الدفق
                except asyncio.IncompleteReadError:
                    break
        finally:
            await self._cleanup_connection()

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
        """يُشغل مستمع UDS وارد ويوجه الطلبات للمعالج المسجل."""
        if self.direction != Direction.INBOUND:
            raise TransportError(ErrorType.PERMANENT, "serve() requires INBOUND direction")
        
        self._handler = handler
        
        # تنظيف مقبس قديم إن وُجد
        if os.path.exists(self.socket_path):
            try:
                os.remove(self.socket_path)
            except OSError:
                pass
                
        self._server = await asyncio.start_unix_server(
            self._handle_client, path=self.socket_path
        )
        logger.info(f"UDS inbound listener started on {self.socket_path}")
        async with self._server:
            await self._server.serve_forever()

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """يدير دورة حياة عميل وارد واحد عبر UDS."""
        ctx = TransportContext(
            session_id=f"uds-{os.path.basename(self.socket_path)}",
            correlation_id="auto",
            stream_offset=0
        )
        try:
            while True:
                try:
                    payload = await asyncio.wait_for(reader.readline(), timeout=self.timeout)
                except (asyncio.IncompleteReadError, asyncio.TimeoutError):
                    break
                    
                if not payload:
                    break
                    
                if self._handler:
                    try:
                        response = await self._handler(payload.rstrip(b"\n"), ctx)
                        writer.write(response + b"\n")
                        await writer.drain()
                    except Exception as e:
                        logger.error(f"UDS handler error: {e}")
                        error_payload = json.dumps({"error": str(e)}).encode()
                        writer.write(error_payload + b"\n")
                        await writer.drain()
                        break
        finally:
            with suppress(Exception):
                writer.close()
                await writer.wait_closed()

    async def close(self) -> None:
        """يُغلق الخادم الوارد ويحرر موارد المقابس والملفات."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
            
        await self._cleanup_connection()
        
        with suppress(OSError):
            if os.path.exists(self.socket_path):
                os.remove(self.socket_path)
                
        logger.debug("UDS transporter resources released")

    async def __aenter__(self) -> UDSTransporter:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()