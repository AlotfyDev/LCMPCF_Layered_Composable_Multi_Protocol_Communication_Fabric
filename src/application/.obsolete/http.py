from __future__ import annotations

import json
from typing import AsyncIterator, Awaitable, Callable

import httpx
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import Response, StreamingResponse
import uvicorn

from ..Transporters.base import BaseTransporter, Direction
from .http_errors import (
    HTTPStatusError,
    RateLimitTransportError,
    http_status_to_error,
    is_retryable_http_status,
)
from ..presentation.request_types import (
    HTTPRequest,
    TransportChunk,
    TransportError,
    TransportRequest,
    TransportResponse,
)
from ..Transporters.retry import RetryPolicy
from ..presentation.sse_parser import parse_sse_line


class HTTPOutboundTransporter(BaseTransporter):

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        default_headers: dict[str, str] | None = None,
        retry_policy: RetryPolicy | None = None,
    ):
        super().__init__(direction=Direction.OUTBOUND)
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._default_headers_dict = default_headers or {}
        try:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(120.0), http2=True)
        except ImportError:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(120.0))
        self._retry = retry_policy or RetryPolicy(
            retryable_errors=(
                TimeoutError,
                ConnectionError,
                RateLimitTransportError,
                HTTPStatusError,
            )
        )

    def _default_headers(self) -> dict[str, str]:
        h = dict(self._default_headers_dict)
        h.setdefault("Content-Type", "application/json")
        if self._api_key:
            h.setdefault("Authorization", f"Bearer {self._api_key}")
        return h

    def _resolve_request(self, request: TransportRequest) -> HTTPRequest:
        if isinstance(request, HTTPRequest):
            return request
        return HTTPRequest(
            url=getattr(request, "url", ""),
            method=getattr(request, "method", "POST"),
            headers=getattr(request, "headers", None),
            json_body=getattr(request, "json_body", None),
            api_key=getattr(request, "api_key", None),
            timeout=request.timeout,
            max_retries=request.max_retries,
            retry_delay=request.retry_delay,
            stream=request.stream,
        )

    async def _do_request(self, req: HTTPRequest) -> TransportResponse:
        url = f"{self._base_url}/{req.url}"
        headers = {**self._default_headers(), **(req.headers or {})}
        body = json.dumps(req.json_body) if req.json_body else None
        try:
            response = await self._client.request(
                req.method,
                url,
                content=body,
                headers=headers,
                timeout=req.timeout,
            )
        except httpx.TimeoutException as e:
            raise TimeoutError(f"HTTP timeout: {e}") from e
        except httpx.ConnectError as e:
            raise ConnectionError(f"HTTP connection error: {e}") from e

        if response.is_success:
            return TransportResponse(
                status_code=response.status_code,
                body=response.text,
                headers=dict(response.headers),
            )

        err = http_status_to_error(response.status_code, response.text)
        if not is_retryable_http_status(response.status_code):
            raise TransportError(err.status_code, str(err)) from err
        raise err

    async def send(self, request: TransportRequest) -> TransportResponse:
        req = self._resolve_request(request)
        return await self._retry.run(lambda: self._do_request(req))

    async def _do_stream(self, req: HTTPRequest) -> AsyncIterator[TransportChunk]:
        url = f"{self._base_url}/{req.url}"
        headers = {**self._default_headers(), **(req.headers or {})}
        body = json.dumps(req.json_body) if req.json_body else None
        try:
            response = await self._client.request(
                req.method,
                url,
                content=body,
                headers=headers,
                timeout=req.timeout,
            )
        except httpx.TimeoutException as e:
            raise TimeoutError(f"HTTP timeout: {e}") from e
        except httpx.ConnectError as e:
            raise ConnectionError(f"HTTP connection error: {e}") from e

        if not response.is_success:
            err = http_status_to_error(response.status_code, response.text)
            if not is_retryable_http_status(response.status_code):
                raise TransportError(err.status_code, str(err)) from err
            raise err

        async def _iterate() -> AsyncIterator[TransportChunk]:
            try:
                async for line in response.aiter_lines():
                    sse = parse_sse_line(line)
                    if sse is None:
                        continue
                    if sse.event == "data":
                        yield TransportChunk(data=sse.data, done=sse.is_done)
                        if sse.is_done:
                            return
                yield TransportChunk(data="", done=True)
            finally:
                await response.aclose()

        return _iterate()

    async def stream(self, request: TransportRequest) -> AsyncIterator[TransportChunk]:
        req = self._resolve_request(request)
        async for chunk in self._retry.run_stream(lambda: self._do_stream(req)):
            yield chunk

    async def close(self) -> None:
        await self._client.aclose()


class HTTPInboundTransporter(BaseTransporter):

    def __init__(self, host: str = "0.0.0.0", port: int = 8000):
        super().__init__(direction=Direction.INBOUND)
        self._host = host
        self._port = port
        self._app = FastAPI()
        self._handler: Callable[[TransportRequest], Awaitable[TransportResponse]] | None = None
        self._server: uvicorn.Server | None = None

    async def send(self, request: TransportRequest) -> TransportResponse:
        raise TransportError(0, f"{type(self).__name__} does not support send()")

    async def stream(self, request: TransportRequest) -> AsyncIterator[TransportChunk]:
        raise TransportError(0, f"{type(self).__name__} does not support stream()")

    async def _handle_request(self, request: Request) -> Response:
        body = await request.json()
        req = HTTPRequest(
            url=str(request.url),
            method=request.method,
            headers=dict(request.headers),
            json_body=body,
        )
        resp = await self._handler(req)
        return Response(
            content=resp.body,
            status_code=resp.status_code,
            headers=resp.headers,
        )

    async def _handle_websocket(self, ws: WebSocket) -> None:
        await ws.accept()
        try:
            data = await ws.receive_json()
            req = HTTPRequest(json_body=data, stream=True)
            resp = await self._handler(req)
            await ws.send_json({"status_code": resp.status_code, "body": resp.body})
        except Exception as e:
            await ws.send_json({"error": str(e)})
        finally:
            await ws.close()

    async def _handle_sse(self, request: Request) -> StreamingResponse:
        async def event_stream():
            try:
                body = await request.json()
            except Exception:
                body = {}

            req = HTTPRequest(json_body=body, stream=True)
            try:
                resp = await self._handler(req)
                yield f"data: {resp.body}\n\n"
                yield f"data: [DONE]\n\n"
            except TransportError as e:
                yield f"data: {json.dumps({'error': str(e), 'code': e.status_code})}\n\n"
                yield f"data: [DONE]\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
                yield f"data: [DONE]\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    async def _health(self) -> dict[str, str]:
        return {"status": "ok"}

    async def serve(self, handler: Callable[[TransportRequest], Awaitable[TransportResponse]]) -> None:
        self._handler = handler
        self._app.post("/")(self._handle_request)
        self._app.post("/v1/generate")(self._handle_request)
        self._app.post("/v1/sse")(self._handle_sse)
        self._app.get("/health")(self._health)
        self._app.websocket("/v1/stream")(self._handle_websocket)
        config = uvicorn.Config(self._app, host=self._host, port=self._port, log_level="info", http="auto")
        self._server = uvicorn.Server(config)
        await self._server.serve()

    async def close(self) -> None:
        if self._server:
            self._server.should_exit = True
