from __future__ import annotations

import asyncio
import json
import sys
from typing import Any, AsyncIterator, Awaitable, Callable

from ..Transporters.base import BaseTransporter, Direction
from ..presentation.request_types import (
    CLIRequest,
    TransportChunk,
    TransportError,
    TransportRequest,
    TransportResponse,
)
from ..Transporters.retry import RetryPolicy
from ..Transporters.subprocess import SubprocessError, SubprocessManager


class CLIOutboundTransporter(BaseTransporter):

    def __init__(
        self,
        binary: str,
        args: list[str] | None = None,
        retry_policy: RetryPolicy | None = None,
    ):
        super().__init__(direction=Direction.OUTBOUND)
        self._proc = SubprocessManager(binary, args)
        self._retry = retry_policy or RetryPolicy()

    def _resolve_request(self, request: TransportRequest) -> CLIRequest:
        if isinstance(request, CLIRequest):
            return request
        return CLIRequest(
            command=getattr(request, "command", None),
            stdin=getattr(request, "stdin", None)
            or json.dumps(getattr(request, "json_body", {})),
            env=getattr(request, "env", None),
            cwd=getattr(request, "cwd", None),
            timeout=request.timeout,
            max_retries=request.max_retries,
            retry_delay=request.retry_delay,
            stream=request.stream,
        )

    def _get_stdin_bytes(self, req: CLIRequest) -> bytes:
        return (req.stdin or "").encode()

    async def send(self, request: TransportRequest) -> TransportResponse:
        req = self._resolve_request(request)
        stdin_bytes = self._get_stdin_bytes(req)
        try:
            stdout, stderr = await self._proc.send(stdin_bytes, req.timeout)
        except SubprocessError as e:
            raise TransportError(e.status_code, str(e)) from e

        body = stdout.decode()
        returncode = self._proc._proc.returncode if self._proc._proc else 0
        if returncode != 0:
            err_msg = stderr.decode() or body
            raise self._build_error(returncode, err_msg)

        return TransportResponse(status_code=returncode, body=body)

    async def stream(self, request: TransportRequest) -> AsyncIterator[TransportChunk]:
        req = self._resolve_request(request)
        stdin_bytes = self._get_stdin_bytes(req)
        await self._proc.spawn(stdin_bytes)
        async for chunk in self._proc.stream(stdin_bytes, req.timeout):
            yield chunk

    async def close(self) -> None:
        await self._proc.close()


class CLIInboundTransporter(BaseTransporter):

    def __init__(self):
        super().__init__(direction=Direction.INBOUND)
        self._handler: Callable[[TransportRequest], Awaitable[TransportResponse]] | None = None

    async def send(self, request: TransportRequest) -> TransportResponse:
        raise TransportError(0, f"{type(self).__name__} does not support send()")

    async def stream(self, request: TransportRequest) -> AsyncIterator[TransportChunk]:
        raise TransportError(0, f"{type(self).__name__} does not support stream()")

    def _build_rpc_error(self, code: int, message: str, rpc_id: Any = None, data: str | None = None) -> dict:
        error = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        return {"jsonrpc": "2.0", "error": error, "id": rpc_id}

    def _build_rpc_result(self, result: Any, rpc_id: Any) -> dict:
        return {"jsonrpc": "2.0", "result": result, "id": rpc_id}

    def _write_response(self, response: dict) -> None:
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()

    async def serve(self, handler: Callable[[TransportRequest], Awaitable[TransportResponse]]) -> None:
        self._handler = handler
        loop = asyncio.get_event_loop()

        while True:
            line = await loop.run_in_executor(None, sys.stdin.readline)
            if not line:
                break

            raw = line.strip()
            if not raw:
                continue

            # Step 1: Parse JSON
            try:
                rpc = json.loads(raw)
            except json.JSONDecodeError:
                self._write_response(self._build_rpc_error(-32700, "Parse error", None))
                continue

            # Step 2: Handle batch vs single request
            requests = rpc if isinstance(rpc, list) else [rpc]
            responses = []

            for request_obj in requests:
                # Step 3: Validate request structure
                if not isinstance(request_obj, dict) or request_obj.get("jsonrpc") != "2.0" or not request_obj.get("method"):
                    err_id = request_obj.get("id") if isinstance(request_obj, dict) else None
                    responses.append(self._build_rpc_error(-32600, "Invalid Request", err_id))
                    continue

                method = request_obj["method"]
                params = request_obj.get("params", {})
                rpc_id = request_obj.get("id")

                # Notifications (no id) — don't send response
                is_notification = rpc_id is None

                # Step 4: Route by method
                if method not in ("send", "stream", "health"):
                    if not is_notification:
                        responses.append(self._build_rpc_error(-32601, f"Method not found: {method}", rpc_id))
                    continue

                # Step 5: Build internal request
                control = params if isinstance(params, dict) else {}
                req = TransportRequest(
                    timeout=control.get("timeout", 120.0),
                    max_retries=control.get("max_retries", 3),
                    retry_delay=control.get("retry_delay", 1.0),
                    stream=method == "stream",
                )
                req.json_body = params  # type: ignore[attr-defined]

                # Step 6: Dispatch
                try:
                    if method == "health":
                        if not is_notification:
                            responses.append(self._build_rpc_result({"status": "ok"}, rpc_id))
                        continue

                    resp = await self._handler(req)
                    if not is_notification:
                        responses.append(self._build_rpc_result(resp.body, rpc_id))
                except TransportError as e:
                    if not is_notification:
                        responses.append(self._build_rpc_error(e.status_code, str(e), rpc_id))
                except Exception as e:
                    if not is_notification:
                        responses.append(self._build_rpc_error(-32603, "Internal error", rpc_id, str(e)))

            # Step 7: Write response(s)
            if responses:
                output = responses if isinstance(rpc, list) else responses[0]
                self._write_response(output)

    async def close(self) -> None:
        self._handler = None
