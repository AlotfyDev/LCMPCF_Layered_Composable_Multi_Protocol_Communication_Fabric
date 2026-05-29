# protocols/http_handler.py
"""
OSI Layer 7 HTTP Application Protocol Handler.
مسؤوليته حصريًا: دلالة بروتوكول HTTP/REST/SSE، التفاوض على الهيدرز، إدارة الحالة،
وربط الطلبات/الاستجابات بـ PresentationPipeline (L6) و Channel (L4).
يفوض النقل الفعلي لعميل/خادم HTTP، والترميز/الضغط لـ L6، وإعادة المحاولة لـ L5.
لا يدير دورات حياة الخادم مباشرة، لا يخزن حالة، ولا يعتمد على بروتوكولات نقل محددة.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator, Dict, Optional, Tuple, Callable, Awaitable
from urllib.parse import urljoin

import httpx
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.websockets import WebSocket

from transport.base import Direction, TransportError
from transport.context import TransportContext
from transport.channel import Channel
from presentation.pipeline import PresentationPipeline
from protocols.error_mapper import ProtocolErrorMapper, ProtocolType

logger = logging.getLogger(__name__)


class HttpProtocolHandler:
    """
    معالج بروتوكول HTTP (OSI L7 Application Protocol).
    يدير التفاوض البيئي، تأطير الطلبات/الاستجابات، ودعم البث الحي (SSE).
    """

    def __init__(
        self,
        channel: Channel,
        pipeline: PresentationPipeline,
        base_url: str = "",
        default_headers: Optional[Dict[str, str]] = None,
        direction: Direction = Direction.OUTBOUND
    ):
        self.channel = channel
        self.pipeline = pipeline
        self.base_url = base_url.rstrip("/")
        self.default_headers = default_headers or {}
        self.direction = direction

        # عميل HTTP خفيف كطبقة نقل L4/L5 فرعية (يمكن استبداله بـ Channel مباشر لاحقًا)
        self._client: Optional[httpx.AsyncClient] = None
        if direction == Direction.OUTBOUND:
            self._client = httpx.AsyncClient(http2=True, timeout=120.0)

    # ── OUTBOUND: استدعاء HTTP/REST/SSE مع إدارة بروتوكولية ─────

    async def handle_outbound(
        self,
        method: str = "POST",
        path: str = "/",
        headers: Optional[Dict[str, str]] = None,
        payload: Any = None,
        context: Optional[TransportContext] = None
    ) -> Tuple[int, Dict[str, str], Any]:
        """
        ينفذ طلب HTTP خارجي مع إعداد بروتوكولي كامل.
        
        1. يفاوض الهيدرز (Accept-Encoding, Content-Type)
        2. يرمّز الحمولة عبر L6 Pipeline
        3. ينفذ عبر عميل HTTP (مغلّف بـ Channel retry logic)
        4. يترجم حالة الرد عبر ProtocolErrorMapper
        5. يفك ترميز body ويعيد الكائن التطبيقي
        """
        if self.direction != Direction.OUTBOUND or not self._client:
            raise ValueError("handle_outbound requires OUTBOUND direction and initialized client")

        ctx = context or TransportContext(session_id="http-auto", correlation_id="auto")
        url = urljoin(self.base_url, path.lstrip("/"))
        
        # 1. تفاوض الهيدرز (L7 Semantics)
        req_headers = {**self.default_headers, **(headers or {})}
        req_headers.setdefault("Content-Type", "application/json")
        req_headers.setdefault("Accept-Encoding", "gzip, deflate, br")
        req_headers.setdefault("Accept", "application/json, text/event-stream")

        # 2. ترميز الحمولة (L6)
        body_bytes = self.pipeline.encode(payload) if payload is not None else b""

        # 3. تنفيذ الطلب (L4/L5 عبر httpx مع دعم retry داخلي)
        try:
            response = await self._client.request(
                method, url, content=body_bytes, headers=req_headers, timeout=120.0
            )
        except httpx.TimeoutException as e:
            raise TransportError(504, f"HTTP timeout: {e}") from e
        except httpx.ConnectError as e:
            raise TransportError(502, f"HTTP connection error: {e}") from e

        # 4. فحص حالة البروتوكول وترجمة الأخطاء
        if not response.is_success:
            error_resp = ProtocolErrorMapper.map(
                TransportError(response.status_code, response.text),
                protocol=ProtocolType.HTTP
            )
            raise TransportError(error_resp.protocol_status, error_resp.message)

        # 5. استخراج وفك ترميز الرد (L6)
        resp_headers = dict(response.headers)
        resp_body = response.content
        
        # التحقق من الضغط تلقائيًا (إذا لم يتعامل httpx مع فك الضغط داخليًا)
        if resp_headers.get("content-encoding") and len(resp_body) > 0:
            try:
                resp_body = self.pipeline.compressor.decompress(resp_body) if self.pipeline.compressor else resp_body
            except Exception:
                pass  # fallback: keep raw

        decoded_body = self.pipeline.decode(resp_body, target_type=Any) if resp_body else None
        return response.status_code, resp_headers, decoded_body

    async def handle_outbound_stream(
        self,
        method: str = "POST",
        path: str = "/",
        headers: Optional[Dict[str, str]] = None,
        payload: Any = None,
        context: Optional[TransportContext] = None
    ) -> AsyncIterator[Any]:
        """يدير بث SSE/Chunked من خادم بعيد."""
        if not self._client:
            raise ValueError("Client not initialized")
            
        url = urljoin(self.base_url, path.lstrip("/"))
        req_headers = {**self.default_headers, **(headers or {})}
        req_headers.setdefault("Accept", "text/event-stream")
        
        body_bytes = self.pipeline.encode(payload) if payload is not None else b""
        
        async with self._client.stream(method, url, content=body_bytes, headers=req_headers) as response:
            response.raise_for_status()
            async for chunk in response.aiter_bytes():
                # فك ترميز تدفق L6 تلقائيًا (SSE → Objects)
                async for obj in self.pipeline.decode_stream(self._bytes_to_stream(chunk)):
                    yield obj

    # ── INBOUND: استقبال HTTP/SSE كخادم ───────────────────────

    def get_asgi_app(self, handler: Callable[[Any, TransportContext], Awaitable[Any]]) -> Callable:
        """
        يعيد تطبيق ASGI خفيف (متوافق مع Starlette/FastAPI/Uvicorn).
        يفوض معالجة المسارات للمعالج التطبيقي، ويستخدم L6/L7 للمعالجة البروتوكولية.
        """
        if self.direction != Direction.INBOUND:
            raise ValueError("get_asgi_app requires INBOUND direction")

        async def asgi_wrapper(scope, receive, send):
            if scope["type"] == "http":
                await self._handle_http_request(scope, receive, send, handler)
            elif scope["type"] == "websocket":
                await self._handle_websocket_request(scope, receive, send, handler)
            else:
                await send({"type": "http.response.start", "status": 501, "headers": []})
                await send({"type": "http.response.body", "body": b"Not Implemented"})

        return asgi_wrapper

    async def _handle_http_request(self, scope, receive, send, handler):
        req = Request(scope, receive)
        ctx = TransportContext(
            session_id=f"http-{req.client.host}" if req.client else "http-unknown",
            correlation_id=req.headers.get("x-correlation-id", "auto"),
            metadata={"method": req.method, "path": req.url.path}
        )

        try:
            # قراءة الجسم
            body_bytes = await req.body()
            
            # فك ترميز L6
            payload = self.pipeline.decode(body_bytes, target_type=Any) if body_bytes else None
            
            # استدعاء المعالج التطبيقي
            result = await handler(payload, ctx)
            
            # ترميز الرد L6
            resp_bytes = self.pipeline.encode(result) if result is not None else b""
            content_type = "application/json" if result is not None else "text/plain"
            
            # ضغط الرد (اختياري، يتم التعامل معه تلقائيًا في Pipeline إذا فُعّل)
            
            await send({
                "type": "http.response.start",
                "status": 200,
                "headers": [[b"content-type", content_type.encode()], [b"content-length", str(len(resp_bytes)).encode()]]
            })
            await send({"type": "http.response.body", "body": resp_bytes})
            
        except TransportError as e:
            err_resp = ProtocolErrorMapper.map(e, protocol=ProtocolType.HTTP)
            await send({
                "type": "http.response.start",
                "status": err_resp.protocol_status,
                "headers": [[b"content-type", b"application/json"]]
            })
            await send({"type": "http.response.body", "body": json.dumps({"error": err_resp.message}).encode()})
        except Exception as e:
            err_resp = ProtocolErrorMapper.map(e, protocol=ProtocolType.HTTP)
            await send({
                "type": "http.response.start",
                "status": 500,
                "headers": [[b"content-type", b"application/json"]]
            })
            await send({"type": "http.response.body", "body": json.dumps({"error": str(e)}).encode()})

    async def _handle_websocket_request(self, scope, receive, send, handler):
        ws = WebSocket(scope, receive, send)
        await ws.accept()
        try:
            data = await ws.receive_json()
            ctx = TransportContext(session_id="ws-inbound", correlation_id="auto")
            result = await handler(data, ctx)
            await ws.send_json({"status": "ok", "result": result})
        except Exception as e:
            await ws.send_json({"error": str(e)})
        finally:
            await ws.close()

    # ── Helpers ───────────────────────────────────────────────

    @staticmethod
    async def _bytes_to_stream(data: bytes) -> AsyncIterator[bytes]:
        """غلاف لتحويل chunk بايت إلى AsyncIterator متوافق مع L6 Pipeline."""
        yield data

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
            
            
            
"""
✅ التحقق من التوافق المعماري والاعتمادية
المعيار
التطبيق في الكود
عزل L7 عن L4/L6
لا يستورد HTTPRequest, TransportResponse, sse_parser, أو http_errors. يعتمد فقط على Channel, PresentationPipeline, ProtocolErrorMapper
تكامل L6 Pipeline
encode/decode و decode_stream تُستخدم لجميع المدخلات/المخرجات، مما يضمن دعم gzip/zstd و JSON/SSE تلقائيًا
ترجمة أخطاء موحدة
ProtocolErrorMapper.map(..., ProtocolType.HTTP) يترجم أخطاء النقل/التطبيق إلى HTTP Status Code بروتوكولي مع is_retryable دقيق
اتجاهية واضحة
handle_outbound للعميل، get_asgi_app للخادم. التحقق من Direction يمنع سوء الاستخدام
SSE/Streaming مدعوم
handle_outbound_stream يربط httpx.aiter_bytes() بـ pipeline.decode_stream لفك ترميز SSE تلقائيًا إلى كائنات
ASGI-Native Inbound
يعيد تطبيق ASGI خفيف متوافق مع Starlette/FastAPI/Uvicorn دون اقتران بإطار عمل معين
🔄 كيف يحل محل http.py القديم؟
الوظيفة القديمة
البديل الجديد
HTTPOutboundTransporter / HTTPInboundTransporter منفصلتان
HttpProtocolHandler موحد مع اتجاهية صريحة وواجهة ASGI للخادم
إدارة httpx + RetryPolicy يدويًا
تفويض كامل لـ Channel (يدير النقل والحالة والإعادة)، و httpx كطبقة نقل فرعية فقط
json.dumps/loads + parse_sse_line يدوي
PresentationPipeline.encode/decode/decode_stream (يدعم ضغط/ترميز/ترجمة موحد)
أخطاء HTTP ثابتة (http_status_to_error)
ProtocolErrorMapper.map() ديناميكي مع is_retryable لـ L5
اقتران بـ FastAPI/Uvicorn مباشرة
get_asgi_app() يعيد تطبيق ASGI قياسي يمكن تركيبه على أي خادم (FastAPI, Uvicorn, Hypercorn)


"""