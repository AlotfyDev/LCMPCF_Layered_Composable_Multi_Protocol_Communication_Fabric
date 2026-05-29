# adapters/fastapi_router.py
"""
OSI L7 → FastAPI Adapter (Framework Integration Layer).
مسؤوليته حصريًا: ربط معالجات البروتوكولات (L7) بمسارات FastAPI/ASGI،
استخراج الرؤوس/الحمولات، إنشاء سياق الجلسة، وتحويل الأخطاء البروتوكولية
إلى استجابات HTTP معيارية.

✅ لا يحتوي على منطق أعمال أو قواعد نقل.
✅ يعتمد حصريًا على عقود L7/L6 المجردة.
✅ يدعم HTTP/REST، GraphQL، Webhooks، و SSE بشكل موحد.
✅ يحوّل TransportError و ProtocolError إلى JSONResponse/StreamingResponse معياريين.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator, Callable, Dict, Optional

from fastapi import APIRouter, Request, WebSocket, HTTPException
from fastapi.responses import Response, StreamingResponse, JSONResponse
from starlette.status import HTTP_200_OK, HTTP_400_BAD_REQUEST, HTTP_500_INTERNAL_SERVER_ERROR

from transport.context import TransportContext
from presentation.pipeline import PresentationPipeline
from protocols.http_handler import HttpProtocolHandler
from protocols.graphql_handler import GraphQLProtocolHandler
from protocols.webhook_handler import WebhookProtocolHandler
from protocols.error_mapper import ProtocolErrorMapper, ProtocolType
from transport.base import TransportError, Direction

logger = logging.getLogger(__name__)


class FastAPIProtocolRouter:
    """
    محوّل FastAPI لبروتوكولات L7.
    يربط المسارات الشبكية بمعالجات البروتوكولات المجردة، ويدير دورة حياة الطلب/الرد.
    """

    def __init__(
        self,
        pipeline: PresentationPipeline,
        http_handler: Optional[HttpProtocolHandler] = None,
        graphql_handler: Optional[GraphQLProtocolHandler] = None,
        webhook_handler: Optional[WebhookProtocolHandler] = None,
        default_app_handler: Optional[Callable[[Any, TransportContext], Any]] = None
    ):
        self.pipeline = pipeline
        self.http = http_handler
        self.graphql = graphql_handler
        self.webhook = webhook_handler
        self.app_handler = default_app_handler
        self._router = APIRouter()

    @property
    def router(self) -> APIRouter:
        """يعيد كائن التوجيه لدمجه في تطبيق FastAPI الرئيسي."""
        return self._router

    # ── Route Registration ───────────────────────────────────

    def register_routes(
        self,
        prefix: str = "/v1",
        enable_http: bool = True,
        enable_graphql: bool = True,
        enable_webhooks: bool = True,
        enable_sse: bool = True
    ) -> None:
        """يسجل مسارات البروتوكولات على الراوتر مع خيارات تفعيل/تعطيل انتقائية."""
        if enable_http:
            self._router.add_api_route(
                f"{prefix}/{{path:path}}",
                self._handle_http,
                methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
                response_class=Response,
                tags=["HTTP/REST"]
            )
        if enable_graphql:
            self._router.add_api_route(
                f"{prefix}/graphql",
                self._handle_graphql,
                methods=["POST"],
                response_class=JSONResponse,
                tags=["GraphQL"]
            )
        if enable_webhooks:
            self._router.add_api_route(
                f"{prefix}/webhooks/{{event_type}}",
                self._handle_webhook,
                methods=["POST"],
                response_class=JSONResponse,
                tags=["Webhooks"]
            )
        if enable_sse:
            self._router.add_api_route(
                f"{prefix}/stream",
                self._handle_sse,
                methods=["GET", "POST"],
                response_class=StreamingResponse,
                tags=["SSE/Streaming"]
            )

    # ── Protocol-Specific Handlers ───────────────────────────

    async def _handle_http(self, request: Request, path: str) -> Response:
        """يعالج طلبات HTTP/REST القياسية عبر HttpProtocolHandler."""
        ctx = self._build_context(request)
        try:
            body_bytes = await request.body()
            headers = dict(request.headers)
            
            if self.http:
                # تفويض المعالجة لمعالج L7
                status, resp_headers, result = await self.http.handle_outbound(
                    method=request.method,
                    path=f"/{path}",
                    headers=headers,
                    payload=self.pipeline.decode(body_bytes, target_type=Any) if body_bytes else None,
                    context=ctx
                )
                resp_bytes = self.pipeline.encode(result) if result is not None else b""
                return Response(
                    content=resp_bytes,
                    status_code=status,
                    headers={k: str(v) for k, v in resp_headers.items()}
                )
            else:
                # Fallback للمعالج الافتراضي
                result = await self.app_handler(body_bytes, ctx) if self.app_handler else {"status": "no_handler"}
                return JSONResponse(status_code=HTTP_200_OK, content=result)

        except TransportError as e:
            return self._map_error_to_response(e, ProtocolType.HTTP)
        except Exception as e:
            return self._map_error_to_response(e, ProtocolType.HTTP)

    async def _handle_graphql(self, request: Request) -> JSONResponse:
        """يعالج استعلامات GraphQL عبر GraphQLProtocolHandler."""
        ctx = self._build_context(request)
        try:
            body = await request.json()
            if not self.graphql:
                raise TransportError(501, "GraphQL handler not configured")

            # تفويض التنفيذ للمعالج التطبيقي (Resolvers)
            async def _executor(query, variables, op_name, context):
                if self.app_handler:
                    return await self.app_handler({"query": query, "variables": variables, "operationName": op_name}, context)
                return None

            response = await self.graphql.handle_inbound(
                raw_payload=body,
                context=ctx,
                executor=_executor
            )
            return JSONResponse(status_code=HTTP_200_OK, content=response)

        except TransportError as e:
            err = self._map_error_to_dict(e, ProtocolType.GRAPHQL)
            return JSONResponse(status_code=err.get("status", 500), content=err.get("payload"))
        except Exception as e:
            err = self._map_error_to_dict(e, ProtocolType.GRAPHQL)
            return JSONResponse(status_code=500, content=err.get("payload"))

    async def _handle_webhook(self, request: Request, event_type: str) -> JSONResponse:
        """يستقبل Webhooks مع التحقق من التوقيع والتفريد."""
        ctx = self._build_context(request)
        try:
            raw_body = await request.body()
            metadata = {
                "x-webhook-id": request.headers.get("x-webhook-id", ctx.correlation_id),
                "x-webhook-timestamp": request.headers.get("x-webhook-timestamp", "0"),
                "x-webhook-signature": request.headers.get("x-webhook-signature", ""),
                "event_type": event_type
            }
            if not self.webhook:
                raise TransportError(501, "Webhook handler not configured")

            result = await self.webhook.handle_inbound(
                raw_payload=raw_body,
                metadata=metadata,
                context=ctx,
                handler=self.app_handler or (lambda p, c: p)
            )
            return JSONResponse(status_code=HTTP_200_OK, content=result)

        except TransportError as e:
            err = self._map_error_to_dict(e, ProtocolType.WEBHOOK)
            return JSONResponse(status_code=err.get("status", 500), content=err.get("payload"))
        except Exception as e:
            err = self._map_error_to_dict(e, ProtocolType.WEBHOOK)
            return JSONResponse(status_code=500, content=err.get("payload"))

    async def _handle_sse(self, request: Request) -> StreamingResponse:
        """يعالج بث SSE/Chunks عبر تدفق غير متزامن."""
        ctx = self._build_context(request)
        async def event_generator() -> AsyncIterator[str]:
            try:
                body = await request.json() if request.method == "POST" else {}
                if self.app_handler:
                    result = await self.app_handler(body, ctx)
                    # تحويل النتيجة إلى تدفق أحداث SSE
                    yield f"data: {json.dumps(result)}\n\n"
                    yield "data: [DONE]\n\n"
                else:
                    yield "data: {\"status\": \"streaming_disabled\"}\n\n"
            except Exception as e:
                err = self._map_error_to_dict(e, ProtocolType.HTTP)
                yield f"data: {json.dumps(err.get('payload', {'error': str(e)}))}\n\n"
                yield "data: [DONE]\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
        )

    # ── Helpers & Error Mapping ──────────────────────────────

    def _build_context(self, request: Request) -> TransportContext:
        """يُنشئ سياق جلسة موحد من رؤوس الطلب وبيانات العميل."""
        client_ip = request.client.host if request.client else "unknown"
        return TransportContext(
            session_id=f"http-{client_ip}",
            correlation_id=request.headers.get("x-correlation-id", request.headers.get("x-request-id", "auto")),
            metadata={
                "method": request.method,
                "path": request.url.path,
                "user_agent": request.headers.get("user-agent"),
                "content_type": request.headers.get("content-type")
            }
        )

    def _map_error_to_response(self, error: Exception, protocol: ProtocolType) -> Response:
        """يحوّل استثناء إلى استجابة HTTP معيارية عبر ProtocolErrorMapper."""
        err_resp = ProtocolErrorMapper.map(error, protocol=protocol)
        return Response(
            content=json.dumps({"error": err_resp.message, "code": err_resp.protocol_status}).encode(),
            status_code=err_resp.protocol_status,
            headers=err_resp.headers,
            media_type="application/json"
        )

    def _map_error_to_dict(self, error: Exception, protocol: ProtocolType) -> dict:
        """يحوّل استثناء إلى قاموس JSON لـ FastAPI JSONResponse."""
        err_resp = ProtocolErrorMapper.map(error, protocol=protocol)
        return {
            "status": err_resp.protocol_status,
            "payload": {
                "error": err_resp.message,
                "code": err_resp.protocol_status,
                "retry_hint": err_resp.is_retryable
            }
        }
        
        

"""
✅ التحقق من التوافق المعماري
المعيار
التطبيق في الكود
عزل L7 عن Framework
لا منطق أعمال، لا إدارة اتصال شبكي. يعتمد فقط على معالجات L7 المجردة، Pipeline، و ProtocolErrorMapper
DIP & Composition Root
يُحقن handlers و pipeline عند التهيئة. لا يستورد تفاصيل نقل أو جلسة. يعمل كـ Adapter صافي
بروتوكولات متعددة
يدعم HTTP/REST (/{{path}})، GraphQL (/graphql)، Webhooks (/webhooks/{type})، SSE (/stream)
سياق موحد
_build_context() يستخرج correlation-id، client_ip، headers ويُنشئ TransportContext لكل طلب
ترجمة أخطاء موحدة
_map_error_to_response/dict يستخدم ProtocolErrorMapper لتحويل أي استثناء إلى حالة بروتوكول + رؤوس + رسالة
Async & Streaming Safe
يستخدم StreamingResponse مع AsyncIterator آمن لـ SSE، ويتعامل مع أخطاء التدفق دون كسر الحلقة
FastAPI Native
يعتمد على APIRouter، Request/Response، JSONResponse، ويتوافق مع DI و Docs التلقائي
🔄 كيف يندمج مع بقية المعمارية؟

# main.py (مثال تكامل)
from fastapi import FastAPI
from transport.factory import TransportFactory
from transport.config import TransportConfig
from presentation.pipeline import PresentationPipeline
from protocols.http_handler import HttpProtocolHandler
from protocols.graphql_handler import GraphQLProtocolHandler
from protocols.webhook_handler import WebhookProtocolHandler
from adapters.fastapi_router import FastAPIProtocolRouter

app = FastAPI()

# تكوين خط L6/L7
pipeline = PresentationPipeline(...)
http_handler = HttpProtocolHandler(channel=..., pipeline=pipeline, direction=Direction.INBOUND)
graphql_handler = GraphQLProtocolHandler(pipeline=pipeline, direction=Direction.INBOUND)
webhook_handler = WebhookProtocolHandler(pipeline=pipeline, direction=Direction.INBOUND, shared_secret="...")

# تركيب الراوتر
router_adapter = FastAPIProtocolRouter(
    pipeline=pipeline,
    http_handler=http_handler,
    graphql_handler=graphql_handler,
    webhook_handler=webhook_handler,
    default_app_handler=my_actor_logic  # دالة BaseActor أو منطق التطبيق
)
router_adapter.register_routes(prefix="/api")
app.include_router(router_adapter.router)


"""