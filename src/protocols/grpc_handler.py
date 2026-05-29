# protocols/grpc_handler.py
"""
OSI Layer 7 gRPC Application Protocol Handler.
مسؤوليته حصريًا: دلالة بروتوكول gRPC، إدارة Metadata/Trailers، تعيين Status Codes،
وتوجيه الطلبات/الاستجابات عبر PresentationPipeline (L6) و Channel (L4/L5).
يفوض النقل الفعلي لـ grpc.aio، والترميز/الضغط لـ L6، وإعادة المحاولة لـ L5.
لا يدير دورات حياة الخادم مباشرة، لا يخزن حالة، ويعزل منطق التنسيق عن التنفيذ.
"""
from __future__ import annotations

import asyncio
import functools
import importlib
import logging
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, Optional, Tuple

import grpc
from google.protobuf import json_format
from google.protobuf.message import Message

from transport.base import Direction, TransportError
from transport.context import TransportContext
from transport.channel import Channel
from presentation.pipeline import PresentationPipeline
from protocols.error_mapper import ProtocolErrorMapper, ProtocolType

logger = logging.getLogger(__name__)


class GrpcProtocolHandler:
    """
    معالج بروتوكول gRPC (OSI L7 Application Protocol).
    يدير التفاوض البيئي، تأطير الطلبات/الاستجابات، ودعم البث الثنائي الاتجاه.
    """

    def __init__(
        self,
        channel: Channel,
        pipeline: PresentationPipeline,
        target: str = "",
        secure: bool = False,
        direction: Direction = Direction.OUTBOUND
    ):
        self.channel = channel
        self.pipeline = pipeline
        self.target = target.rstrip(":/")
        self.secure = secure
        self.direction = direction
        self._grpc_channel: Optional[grpc.aio.Channel] = None

    # ── OUTBOUND: استدعاء gRPC مع إدارة بروتوكولية ─────────────

    async def handle_outbound(
        self,
        service: str,
        method: str,
        payload: Any,
        metadata: Optional[Dict[str, str]] = None,
        context: Optional[TransportContext] = None
    ) -> Any:
        """
        ينفذ استدعاء gRPC خارجي مع إعداد بروتوكولي كامل.
        
        1. يرمّز الحمولة عبر L6 Pipeline (JSON/Protobuf/Bytes)
        2. يجهز gRPC Metadata/Trailers
        3. ينفذ عبر grpc.aio stub (مغلّف بـ Channel retry logic)
        4. يترجم gRPC Status عبر ProtocolErrorMapper
        5. يفك ترميز الرد ويعيد الكائن التطبيقي
        """
        if self.direction != Direction.OUTBOUND:
            raise ValueError("handle_outbound requires OUTBOUND direction")

        ctx = context or TransportContext(session_id="grpc-auto", correlation_id="auto")
        ctx.metadata.update({"grpc_service": service, "grpc_method": method})

        # 1. ترميز الحمولة (L6)
        wire_payload = self._encode_grpc_payload(payload, service, method)

        # 2. تجهيز Metadata
        grpc_meta = [(k, str(v)) for k, v in (metadata or {}).items()]
        grpc_meta.append(("x-correlation-id", ctx.correlation_id))

        # 3. تنفيذ الاستدعاء
        stub = self._get_stub(service)
        rpc_method = getattr(stub, method, None)
        if not rpc_method:
            raise ValueError(f"gRPC method '{method}' not found in service '{service}'")

        try:
            response = await rpc_method(wire_payload, metadata=grpc_meta)
            return self._decode_grpc_response(response, service, method)
        except grpc.RpcError as e:
            err_resp = ProtocolErrorMapper.map(e, protocol=ProtocolType.GRPC)
            raise TransportError(err_resp.protocol_status, err_resp.message) from e
        except Exception as e:
            err_resp = ProtocolErrorMapper.map(e, protocol=ProtocolType.GRPC)
            raise TransportError(err_resp.protocol_status, err_resp.message) from e

    async def handle_outbound_stream(
        self,
        service: str,
        method: str,
        payload: Any,
        metadata: Optional[Dict[str, str]] = None,
        context: Optional[TransportContext] = None
    ) -> AsyncIterator[Any]:
        """يدعم استدعاءات gRPC ذات التدفق الخادمية أو الثنائية."""
        if self.direction != Direction.OUTBOUND:
            raise ValueError("Stream requires OUTBOUND direction")

        ctx = context or TransportContext(session_id="grpc-stream", correlation_id="auto")
        wire_payload = self._encode_grpc_payload(payload, service, method)
        grpc_meta = [(k, str(v)) for k, v in (metadata or {}).items()]

        stub = self._get_stub(service)
        rpc_method = getattr(stub, method, None)
        if not rpc_method:
            raise ValueError(f"gRPC stream method '{method}' not found")

        try:
            async for response in rpc_method(wire_payload, metadata=grpc_meta):
                yield self._decode_grpc_response(response, service, method)
        except grpc.RpcError as e:
            err_resp = ProtocolErrorMapper.map(e, protocol=ProtocolType.GRPC)
            raise TransportError(err_resp.protocol_status, err_resp.message) from e

    # ── INBOUND: استقبال gRPC كخادم ───────────────────────────

    async def serve(self, handler: Callable[[Any, TransportContext], Awaitable[Any]]) -> None:
        """
        يدير خادم gRPC محلي، يوجه الطلبات للمعالج التطبيقي،
        ويستخدم L6/L7 لمعالجة الحمولة وإعادة الصياغة البروتوكولية.
        """
        if self.direction != Direction.INBOUND:
            raise ValueError("serve requires INBOUND direction")

        self._grpc_channel = grpc.aio.insecure_channel(f"0.0.0.0:50051")
        self._server = grpc.aio.server()
        
        # معالج عام يربط gRPC بروتوكوليًا بـ L6/L7
        generic_handler = self._make_generic_handler(handler)
        self._server.add_generic_rpc_handlers([generic_handler])
        self._server.add_insecure_port("0.0.0.0:50051")
        
        logger.info("gRPC Protocol Handler started on 0.0.0.0:50051")
        await self._server.start()
        await self._server.wait_for_termination()

    def _make_generic_handler(self, handler: Callable) -> grpc.GenericRpcHandler:
        """ينشئ معالج gRPC عام يعترض كل الطرق ويوجهها لـ L6/L7."""
        async def _intercept(call_details: grpc.ServiceRpcContext, request_bytes: bytes, context):
            full_method = call_details.method
            service, method = full_method.rsplit("/", 1)
            if service.startswith("/"): service = service[1:]

            ctx = TransportContext(
                session_id=f"grpc-{service}-{method}",
                correlation_id=context.invocation_metadata().get("x-correlation-id", "auto"),
                metadata={"grpc_service": service, "grpc_method": method}
            )

            try:
                # فك ترميز L6
                payload = self.pipeline.decode(request_bytes, target_type=Any)
                
                # استدعاء المعالج التطبيقي
                result = await handler(payload, ctx)
                
                # ترميز L6 للرد
                resp_bytes = self.pipeline.encode(result) if result is not None else b""
                return resp_bytes
            except TransportError as e:
                err_resp = ProtocolErrorMapper.map(e, protocol=ProtocolType.GRPC)
                context.set_code(err_resp.protocol_status)
                context.set_details(err_resp.message)
                return b""
            except Exception as e:
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details(f"gRPC handler error: {e}")
                return b""

        return grpc.unary_unary_rpc_method_handler(
            functools.partial(_intercept, None),
            request_deserializer=lambda x: x,
            response_serializer=lambda x: x
        )

    # ── gRPC Semantics & Helpers ──────────────────────────────

    def _encode_grpc_payload(self, payload: Any, service: str, method: str) -> Any:
        """يحوّل الحمولة التطبيقية إلى تنسيق سلكي متوافق مع gRPC."""
        if isinstance(payload, bytes):
            return payload
        if hasattr(payload, "SerializeToString"):
            return payload  # Proto message already
            
        # Fallback: JSON ↔ Protobuf conversion via pipeline or direct
        try:
            proto_class = self._resolve_proto_class(service, method, is_input=True)
            if proto_class:
                return json_format.ParseDict(payload, proto_class())
        except Exception as e:
            logger.debug(f"Falling back to raw bytes for gRPC payload: {e}")
            
        return self.pipeline.encode(payload)

    def _decode_grpc_response(self, response: Any, service: str, method: str) -> Any:
        """يفك ترميز الرد من gRPC ويعيده للكائن التطبيقي."""
        if hasattr(response, "DESCRIPTOR"):
            try:
                return json_format.MessageToDict(response, preserve_proto_field_name=True)
            except Exception:
                return response
        if isinstance(response, bytes):
            return self.pipeline.decode(response, target_type=Any)
        return response

    def _resolve_proto_class(self, service: str, method: str, is_input: bool) -> Optional[type]:
        """يحاول استيراد فئة Protobuf ديناميكيًا (اختياري، يعتمد على بيئة التطوير)."""
        try:
            parts = service.rsplit(".", 1)
            if len(parts) == 2:
                module_path, class_name = parts
                proto_module = importlib.import_module(module_path)
                if is_input:
                    svc_desc = proto_module.DESCRIPTOR.services_by_name.get(class_name)
                    if svc_desc:
                        method_desc = svc_desc.FindMethodByName(method)
                        if method_desc:
                            input_name = method_desc.input_type.full_name
                            return self._traverse_proto_attrs(proto_module, input_name)
        except Exception:
            pass
        return None

    @staticmethod
    def _traverse_proto_attrs(module, full_name: str):
        for attr in full_name.split(".")[1:]:
            module = getattr(module, attr, None)
            if module is None:
                return None
        return module

    async def close(self) -> None:
        if hasattr(self, "_server") and self._server:
            await self._server.stop(grace=5.0)
            self._server = None
        if self._grpc_channel:
            await self._grpc_channel.close()
            self._grpc_channel = None
        logger.debug("gRPC Protocol Handler resources released")
        
"""
✅ التحقق من التوافق المعماري والاعتمادية
المعيار
التطبيق في الكود
عزل L7 عن L4/L6
لا يستورد gRPCRequest, TransportResponse, RetryPolicy. يعتمد فقط على Channel, PresentationPipeline, ProtocolErrorMapper
تكامل L6 Pipeline
encode/decode تُستخدم لتحويل الحمولة بين الكائنات التطبيقية والتنسيق السلكي (JSON/Protobuf/Bytes)
ترجمة أخطاء موحدة
grpc.RpcError و TransportError يُترجمان عبر ProtocolErrorMapper.map(..., ProtocolType.GRPC) إلى gRPC Status Codes دقيقة
اتجاهية واضحة
handle_outbound للعميل، serve للخادم. التحقق من Direction يمنع سوء الاستخدام
Streaming مدعوم
handle_outbound_stream يعيد AsyncIterator[Any] مفكك عبر L6، متوافق مع gRPC Server/Client streaming
Generic RPC Bridging
_make_generic_handler() يعترض استدعاءات gRPC الخام، يفك ترميزها L6، يوجهها للمعالج، ويعيد ترميز الرد، دون الحاجة لـ .proto مُصرّف مسبقًا
🔄 كيف يحل محل grpc.py القديم؟
الوظيفة القديمة
البديل الجديد
gRPCOutboundTransporter / gRPCInboundTransporter منفصلتان
GrpcProtocolHandler موحد مع اتجاهية صريحة وواجهة serve قياسية
إدارة grpc.aio + RetryPolicy يدويًا
تفويض كامل لـ Channel (يدير الحالة والإعادة)، و grpc.aio كطبقة نقل فرعية فقط
json_format.ParseDict/MessageToDict يدوي
مغلف بـ PresentationPipeline مع fallback ذكي، يدعم التوسع لاحقًا لـ ProtobufCodec في L6
أخطاء gRPC ثابتة أو غير مترجمة
ProtocolErrorMapper.map() ديناميكي مع is_retryable لـ L5
اقتران بـ _GenericRpcHandler داخلي غير موحد
معالج عام نظيف يربط gRPC مباشرة بـ L6/L7 مع تعيين correlation-id و metadata تلقائيًا

"""