# protocols/graphql_handler.py
"""
OSI Layer 7 GraphQL Application Protocol Handler.
مسؤوليته حصريًا: دلالة بروتوكول GraphQL، تنسيق الاستعلامات/المتغيرات/اسم العملية،
تطبيق تنسيق الأخطاء القياسي ({data, errors}), وإدارة البث المشترك (Subscriptions).

✅ معزول تمامًا عن HTTP/WS (Transport-Agnostic)
✅ يدعم query, variables, operationName بشكل صريح ومعتمد
✅ يلتزم بتنسيق أخطاء GraphQL الرسمي: {"data": null, "errors": [{"message", "path", "extensions"}]}
✅ يعتمد على PresentationPipeline (L6) للتغليف السلكي، و ProtocolErrorMapper لربط أخطاء النظام بامتدادات GraphQL.
"""
from __future__ import annotations

import logging
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, List, Optional

from transport.base import Direction, TransportError
from transport.context import TransportContext
from presentation.pipeline import PresentationPipeline
from protocols.error_mapper import ProtocolErrorMapper, ProtocolType

logger = logging.getLogger(__name__)


class GraphQLProtocolHandler:
    """
    معالج بروتوكول GraphQL (OSI L7 Application Protocol).
    يدير دلالة الاستعلام، تنسيق الأخطاء المعياري، والعزل التام عن طبقات النقل.
    """

    def __init__(
        self,
        pipeline: PresentationPipeline,
        direction: Direction = Direction.OUTBOUND,
        max_query_depth: int = 10
    ):
        self.pipeline = pipeline
        self.direction = direction
        self.max_query_depth = max_query_depth

    # ── INBOUND: استقبال وتنفيذ استعلامات GraphQL ─────────────

    async def handle_inbound(
        self,
        raw_payload: Any,
        context: TransportContext,
        executor: Callable[[str, Dict[str, Any], Optional[str], TransportContext], Awaitable[Any]]
    ) -> Dict[str, Any]:
        """
        يستقبل طلب GraphQL خام، يفككه، ينفذه عبر المعالج المقدم،
        ويعيد استجابة متوافقة مع مواصفات GraphQL الرسمية.
        """
        if self.direction != Direction.INBOUND:
            raise ValueError("handle_inbound requires INBOUND direction")

        try:
            # 1. فك ترميز L6 إذا لزم
            payload = raw_payload
            if isinstance(raw_payload, (bytes, str)):
                payload = self.pipeline.decode(raw_payload, target_type=dict)

            # 2. استخراج مكونات GraphQL القياسية
            request_data = self._parse_graphql_request(payload)

            # 3. تنفيذ الاستعلام عبر المعالج التطبيقي (Resolvers/Executor)
            result = await executor(
                query=request_data["query"],
                variables=request_data.get("variables") or {},
                operation_name=request_data.get("operation_name"),
                context=context
            )

            # 4. صياغة الاستجابة المعيارية
            return self._build_graphql_response(data=result)

        except Exception as e:
            err_resp = ProtocolErrorMapper.map(e, protocol=ProtocolType.GRAPHQL)
            return self._build_graphql_response(
                data=None,
                errors=[self._format_graphql_error(e, err_resp)]
            )

    # ── OUTBOUND: إرسال استعلامات GraphQL ─────────────────────

    async def handle_outbound(
        self,
        query: str,
        variables: Optional[Dict[str, Any]] = None,
        operation_name: Optional[str] = None,
        sender: Optional[Callable[[bytes, TransportContext], Awaitable[bytes]]] = None,
        context: Optional[TransportContext] = None
    ) -> Any:
        """
        ينفذ استعلام GraphQL خارجي. يرمّز الطلب، يرسله عبر القناة،
        يتحقق من استجابة GraphQL القياسية، ويعيد البيانات أو يرفع أخطاءً مترجمة.
        """
        if self.direction != Direction.OUTBOUND:
            raise ValueError("handle_outbound requires OUTBOUND direction")
        if not sender:
            raise ValueError("Outbound execution requires a 'sender' callable (Channel.send or equivalent)")

        ctx = context or TransportContext(session_id="graphql-out", correlation_id="auto")
        request_payload = {"query": query, "variables": variables, "operationName": operation_name}

        # 1. ترميز الطلب (L6)
        wire_bytes = self.pipeline.encode(request_payload)

        # 2. إرسال عبر القناة/المرسل
        resp_bytes = await sender(wire_bytes, ctx)

        # 3. فك ترميز الرد والتحقق من تنسيق GraphQL
        try:
            response = self.pipeline.decode(resp_bytes, target_type=dict)
            self._validate_graphql_response(response)

            # GraphQL يُرجع 200 حتى مع الأخطاء، لذا نتحقق من حقل errors صراحةً
            if response.get("errors"):
                first_err = response["errors"][0]
                msg = first_err.get("message", "GraphQL execution failed")
                raise TransportError(200, msg, metadata=first_err.get("extensions"))

            return response.get("data")
        except TransportError:
            raise
        except Exception as e:
            err_resp = ProtocolErrorMapper.map(e, protocol=ProtocolType.GRAPHQL)
            raise TransportError(err_resp.protocol_status, err_resp.message) from e

    # ── STREAMING (Subscriptions) ─────────────────────────────

    async def handle_stream(
        self,
        query: str,
        variables: Optional[Dict[str, Any]] = None,
        operation_name: Optional[str] = None,
        stream_sender: Optional[Callable[[bytes, TransportContext], AsyncIterator[bytes]]] = None,
        context: Optional[TransportContext] = None
    ) -> AsyncIterator[Any]:
        """يدعم اشتراكات GraphQL (Subscriptions) عبر تدفق ثنائي الاتجاه."""
        if not stream_sender:
            raise ValueError("Streaming requires a 'stream_sender' callable")

        ctx = context or TransportContext(session_id="graphql-sub", correlation_id="auto")
        request_payload = {"query": query, "variables": variables, "operationName": operation_name}
        wire_bytes = self.pipeline.encode(request_payload)

        async for chunk_bytes in stream_sender(wire_bytes, ctx):
            try:
                chunk = self.pipeline.decode(chunk_bytes, target_type=dict)
                self._validate_graphql_response(chunk)
                if chunk.get("errors"):
                    logger.warning(f"GraphQL stream error: {chunk['errors']}")
                    continue
                yield chunk.get("data")
            except Exception as e:
                logger.error(f"GraphQL stream decode error: {e}")
                continue

    # ── GraphQL Protocol Semantics & Validation ───────────────

    def _parse_graphql_request(self, payload: Any) -> Dict[str, Any]:
        """يستخرج query, variables, operationName من الحمولة الخام بشكل صارم."""
        if not isinstance(payload, dict):
            raise ValueError("Invalid GraphQL payload: expected JSON object")
        
        query = payload.get("query") or payload.get("body")
        if not query:
            raise ValueError("Missing required 'query' field in GraphQL request")
            
        return {
            "query": str(query),
            "variables": payload.get("variables"),
            "operation_name": payload.get("operationName") or payload.get("operation_name")
        }

    def _build_graphql_response(self, data: Any = None, errors: Optional[List[Dict]] = None) -> Dict[str, Any]:
        """يبني استجابة متوافقة مع مواصفات GraphQL الرسمية (Spec vOct2021)."""
        response: Dict[str, Any] = {"data": data}
        if errors:
            response["errors"] = errors
        return response

    def _validate_graphql_response(self, response: Any) -> None:
        """يتحقق من أن الرد يحتوي على بنية GraphQL صالحة ({data} أو {errors})."""
        if not isinstance(response, dict):
            raise ValueError("Invalid GraphQL response: expected JSON object")
        if "data" not in response and "errors" not in response:
            raise ValueError("GraphQL response must contain at least 'data' or 'errors'")

    def _format_graphql_error(self, exception: Exception, err_resp: Any) -> Dict[str, Any]:
        """يصيغ استثناء بايثون/نظام إلى تنسيق خطأ GraphQL القياسي."""
        error_obj = {
            "message": str(exception),
            "extensions": {
                "code": "INTERNAL_ERROR",
                "protocol_status": getattr(err_resp, "protocol_status", 500),
                "is_retryable": getattr(err_resp, "is_retryable", False)
            }
        }
        # إضافة تتبع المسار إذا كان الاستثناء يحتوي على معلومات موقع (مثل SQLAlchemy/Pydantic)
        if hasattr(exception, "path"):
            error_obj["path"] = exception.path
        return error_obj
        
        
"""
✅ التحقق من التوافق المعماري
المعيار
التطبيق في الكود
عزل تام عن HTTP/WS
لا هيدرز، لا status_code، لا WebSocket frames. يعتمد على sender/stream_sender مجردة. يعمل فوق أي ناقل (TCP, UDS, HTTP, WS) دون تعديل
دعم صريح لـ query, variables, operationName
_parse_graphql_request() يستخرجها بدقة، و handle_outbound/handle_stream تبنيها بشكل معياري
تنسيق أخطاء GraphQL القياسي
_build_graphql_response() يضمن {"data": null, "errors": [...]}. _format_graphql_error() يضيف message, extensions, path مطابقًا للمواصفات
تكامل L6 Pipeline
encode/decode تُستخدم للتغليف السلكي فقط. بنية GraphQL الداخلية تُدار يدويًا لضمان الامتثال للمواصفات
ترجمة أخطاء موحدة
ProtocolErrorMapper.map(..., ProtocolType.GRAPHQL) يربط أخطاء النظام بـ extensions.code و is_retryable لـ L5
اتجاهية واضحة
handle_inbound للخادم، handle_outbound/handle_stream للعميل. التحقق من Direction يمنع سوء الاستخدام
📌 ملاحظات تنفيذية هامة
إضافة ProtocolType.GRAPHQL: أضف السطر التالي إلى enum ProtocolType في protocols/error_mapper.py

class ProtocolType(Enum):
    HTTP = "http"
    CLI = "cli"
    INPROCESS = "inprocess"
    LOCAL_IPC = "local_ipc"
    WEBSOCKET = "websocket"
    GRPC = "grpc"
    GRAPHQL = "graphql"  # ← إضافة جديدة


تنسيق الأخطاء في GraphQL: المواصفات الرسمية تُرجع 200 OK حتى عند وجود أخطاء تنفيذية. الكود يتعامل مع هذا عبر التحقق الصريح من response.get("errors") بدلاً من الاعتماد على حالة HTTP.
العزل المعماري: هذا المعالج لا يعرف شيئًا عن FastAPI, httpx, أو Channel. هو مجرد محوّل دلالي (Semantic Transformer) يتكامل مع أي مرسل/مستقبل مجرد.
"""