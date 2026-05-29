from __future__ import annotations

import functools
import importlib
from typing import AsyncIterator, Awaitable, Callable

import grpc
from google.protobuf import json_format

from ..Transporters.base import BaseTransporter, Direction
from ..presentation.request_types import (
    TransportChunk,
    TransportError,
    TransportRequest,
    TransportResponse,
    gRPCRequest,
)
from ..Transporters.retry import RetryPolicy


class gRPCOutboundTransporter(BaseTransporter):

    def __init__(
        self,
        target: str,
        secure: bool = False,
        root_certificates: bytes | None = None,
        private_key: bytes | None = None,
        certificate_chain: bytes | None = None,
        retry_policy: RetryPolicy | None = None,
    ):
        super().__init__(direction=Direction.OUTBOUND)
        self._target = target
        self._secure = secure
        self._root_certificates = root_certificates
        self._private_key = private_key
        self._certificate_chain = certificate_chain
        self._channel: grpc.aio.Channel | None = None
        self._retry = retry_policy or RetryPolicy()

    async def _get_channel(self) -> grpc.aio.Channel:
        if self._channel is None:
            if self._secure:
                creds = grpc.ssl_channel_credentials(
                    root_certificates=self._root_certificates,
                    private_key=self._private_key,
                    certificate_chain=self._certificate_chain,
                ) if self._root_certificates else grpc.ssl_channel_credentials()
                self._channel = grpc.aio.secure_channel(self._target, creds)
            else:
                self._channel = grpc.aio.insecure_channel(self._target)
        return self._channel

    def _resolve_request(self, request: TransportRequest) -> gRPCRequest:
        if isinstance(request, gRPCRequest):
            return request
        raise TransportError(0, f"Expected gRPCRequest, got {type(request).__name__}")

    def _import_proto_module(self, service: str):
        parts = service.rsplit(".", 1)
        if len(parts) != 2:
            raise TransportError(0, f"Invalid service name: {service} (must be fully qualified like 'package.Service')")
        module_path, class_name = parts
        try:
            return importlib.import_module(module_path), class_name
        except ImportError as e:
            raise TransportError(0, f"Protobuf module not found: {module_path} ({e})") from e

    def _get_stub(self, channel: grpc.aio.Channel, service: str):
        proto_module, class_name = self._import_proto_module(service)
        stub_class = getattr(proto_module, f"{class_name}Stub", None)
        if stub_class is None:
            raise TransportError(0, f"Stub class '{class_name}Stub' not found in module '{proto_module.__name__}'")
        return stub_class(channel)

    def _convert_payload(self, payload, service: str, method: str):
        if payload is None or hasattr(payload, "DESCRIPTOR"):
            return payload
        try:
            proto_module, class_name = self._import_proto_module(service)
            svc_desc = proto_module.DESCRIPTOR.services_by_name.get(class_name)
            if svc_desc is not None:
                method_desc = svc_desc.FindMethodByName(method)
                if method_desc is not None:
                    input_type_name = method_desc.input_type.full_name
                    msg_class = proto_module
                    for attr in input_type_name.split(".")[1:]:
                        msg_class = getattr(msg_class, attr, None)
                        if msg_class is None:
                            break
                    if msg_class is not None:
                        return json_format.ParseDict(payload, msg_class())
        except (KeyError, AttributeError, json_format.ParseError) as e:
            raise TransportError(
                0,
                f"Cannot convert dict payload to protobuf for {service}.{method}: {e}. "
                "Pass a protobuf message or ensure the proto module is compiled with descriptors.",
            ) from e

    async def send(self, request: TransportRequest) -> TransportResponse:
        req = self._resolve_request(request)
        channel = await self._get_channel()

        async def _do_call():
            stub = self._get_stub(channel, req.service)
            rpc_method = getattr(stub, req.method)
            payload = self._convert_payload(req.payload, req.service, req.method)
            metadata = list(req.metadata.items()) if req.metadata else None
            timeout = req.timeout if req.timeout < 3600 else None
            response = await rpc_method(payload, timeout=timeout, metadata=metadata)
            body = response.SerializeToString().decode("latin-1") if hasattr(response, "SerializeToString") else str(response)
            return TransportResponse(status_code=0, body=body)

        try:
            return await self._retry.run(_do_call)
        except TransportError:
            raise
        except Exception as e:
            raise TransportError(0, f"gRPC call failed: {e}") from e

    async def stream(self, request: TransportRequest) -> AsyncIterator[TransportChunk]:
        req = self._resolve_request(request)
        channel = await self._get_channel()

        async def _do_stream():
            stub = self._get_stub(channel, req.service)
            rpc_method = getattr(stub, req.method)
            payload = self._convert_payload(req.payload, req.service, req.method)
            metadata = list(req.metadata.items()) if req.metadata else None
            timeout = req.timeout if req.timeout < 3600 else None
            async for response in rpc_method(payload, timeout=timeout, metadata=metadata):
                body = response.SerializeToString().decode("latin-1") if hasattr(response, "SerializeToString") else str(response)
                yield TransportChunk(data=body)
            yield TransportChunk(data="", done=True)

        try:
            async for chunk in self._retry.run_stream(_do_stream):
                yield chunk
        except TransportError:
            raise
        except Exception as e:
            raise TransportError(0, f"gRPC stream failed: {e}") from e

    async def close(self) -> None:
        if self._channel:
            await self._channel.close()
            self._channel = None


class _GenericRpcHandler(grpc.GenericRpcHandler):
    """Dispatches any incoming gRPC method to a generic handler function.

    This bridges gRPC's typed servicer model with the transport layer's
    generic handler pattern (Callable[[TransportRequest], TransportResponse]).
    Requests arrive as raw bytes; the user's handler receives them in a
    gRPCRequest and returns a TransportResponse with body as bytes.
    """

    def __init__(self, handler_fn):
        self._handler_fn = handler_fn

    def service(self, handler_call_details):
        return grpc.unary_unary_rpc_method_handler(
            functools.partial(self._handle_method, handler_call_details),
            request_deserializer=lambda x: x,
            response_serializer=lambda x: x,
        )

    async def _handle_method(self, handler_call_details, request_bytes, context):
        full_method = handler_call_details.method
        service, method = full_method.rsplit("/", 1)
        if service.startswith("/"):
            service = service[1:]

        grpc_req = gRPCRequest(
            service=service,
            method=method,
            payload=request_bytes,
            metadata=dict(handler_call_details.invocation_metadata),
            timeout=context.time_remaining() or 120.0,
        )

        response: TransportResponse = await self._handler_fn(grpc_req)

        if isinstance(response.body, bytes):
            return response.body
        if hasattr(response.body, "SerializeToString"):
            return response.SerializeToString()
        return str(response.body).encode("utf-8")


class gRPCInboundTransporter(BaseTransporter):

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 50051,
        secure: bool = False,
        root_certificates: bytes | None = None,
        private_key: bytes | None = None,
        certificate_chain: bytes | None = None,
        max_workers: int = 10,
    ):
        super().__init__(direction=Direction.INBOUND)
        self._host = host
        self._port = port
        self._secure = secure
        self._root_certificates = root_certificates
        self._private_key = private_key
        self._certificate_chain = certificate_chain
        self._max_workers = max_workers
        self._server: grpc.aio.Server | None = None
        self._handler: Callable[[TransportRequest], Awaitable[TransportResponse]] | None = None

    async def send(self, request: TransportRequest) -> TransportResponse:
        raise TransportError(0, f"{type(self).__name__} does not support send()")

    async def stream(self, request: TransportRequest) -> AsyncIterator[TransportChunk]:
        raise TransportError(0, f"{type(self).__name__} does not support stream()")

    async def serve(self, handler: Callable[[TransportRequest], Awaitable[TransportResponse]]) -> None:
        self._handler = handler
        self._server = grpc.aio.server()
        addr = f"{self._host}:{self._port}"

        self._server.add_generic_rpc_handlers([_GenericRpcHandler(handler)])

        if self._secure:
            creds = grpc.ssl_server_credentials(
                [(self._private_key, self._certificate_chain)],
                root_certificates=self._root_certificates,
                require_client_auth=True,
            ) if self._root_certificates else grpc.ssl_server_credentials(
                [(self._private_key, self._certificate_chain)]
            )
            self._server.add_secure_port(addr, creds)
        else:
            self._server.add_insecure_port(addr)
        await self._server.start()

    async def close(self) -> None:
        if self._server:
            await self._server.stop(grace=5)
            self._server = None
