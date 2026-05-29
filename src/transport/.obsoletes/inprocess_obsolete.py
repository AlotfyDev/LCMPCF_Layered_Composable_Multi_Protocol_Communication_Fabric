from __future__ import annotations

import asyncio
import inspect
from typing import Any, AsyncIterator, Awaitable, Callable, Literal

from .base import BaseTransporter, Direction
from ..presentation.request_types import (
    InProcessRequest,
    TransportChunk,
    TransportError,
    TransportResponse,
    TransportRequest,
)

YieldMode = Literal["none", "asyncio", "thread"] | None


class InProcessTransporter(BaseTransporter):
    """In-process function call transport.

    KEY DESIGN: callable and yield_mode are INDEPENDENT variables.
      - callable: the function to call (any callable, sync or async)
      - yield_mode: HOW to schedule the call:
          None / "none" -> direct await callable(*args, **kwargs)
          "asyncio"     -> asyncio.sleep(0); await callable(*args, **kwargs)
          "thread"      -> await asyncio.to_thread(callable, *args, **kwargs)

    Supports both OUTBOUND (we call the function) and INBOUND (we ARE the function).
    """

    def __init__(
        self,
        callable: Callable[..., Any] | None = None,
        yield_mode: YieldMode = None,
        direction: Direction = Direction.OUTBOUND,
    ):
        super().__init__(direction)
        self._callable = callable
        self._yield_mode = yield_mode
        self._inbound_handler: Callable[[TransportRequest], Awaitable[TransportResponse]] | None = None

    # ── Configuration ──────────────────────────────────────

    @property
    def callable(self) -> Callable[..., Any] | None:
        return self._callable

    @callable.setter
    def callable(self, value: Callable[..., Any] | None) -> None:
        self._callable = value

    @property
    def yield_mode(self) -> YieldMode:
        return self._yield_mode

    @yield_mode.setter
    def yield_mode(self, value: YieldMode) -> None:
        self._yield_mode = value

    # ── Helpers ────────────────────────────────────────────

    def _resolve_request(self, request: TransportRequest) -> InProcessRequest:
        """Ensure we have an InProcessRequest with resolved callable + args."""
        if isinstance(request, InProcessRequest):
            callable = request.callable or self._callable
            if callable is None:
                raise TransportError(0, "No callable provided -- set via constructor, property, or InProcessRequest.callable")
            return InProcessRequest(
                timeout=request.timeout,
                max_retries=request.max_retries,
                retry_delay=request.retry_delay,
                stream=request.stream,
                callable=callable,
                args=request.args,
                kwargs=request.kwargs,
                yield_mode=request.yield_mode or self._yield_mode,
            )
        if self._callable is None:
            raise TransportError(0, "No callable provided. Set via constructor or InProcessRequest.callable")
        return InProcessRequest(
            timeout=request.timeout,
            max_retries=request.max_retries,
            retry_delay=request.retry_delay,
            stream=request.stream,
            callable=self._callable,
            args=(),
            kwargs={},
            yield_mode=self._yield_mode,
        )

    async def _execute(self, req: InProcessRequest) -> Any:
        """Execute the callable with the appropriate yield mode."""
        callable = req.callable
        args = req.args or ()
        kwargs = req.kwargs or {}
        mode = req.yield_mode or self._yield_mode

        if mode == "thread":
            result = await asyncio.to_thread(callable, *args, **kwargs)
        elif mode == "asyncio":
            await asyncio.sleep(0)
            if asyncio.iscoroutinefunction(callable):
                result = await callable(*args, **kwargs)
            else:
                result = callable(*args, **kwargs)
        else:
            if asyncio.iscoroutinefunction(callable):
                result = await callable(*args, **kwargs)
            else:
                result = callable(*args, **kwargs)

        return result

    # ── Outbound ───────────────────────────────────────────

    async def send(self, request: TransportRequest) -> TransportResponse:
        """Execute the callable and return response."""
        req = self._resolve_request(request)
        try:
            result = await asyncio.wait_for(
                self._execute(req),
                timeout=req.timeout,
            )
        except asyncio.TimeoutError:
            raise TransportError(0, f"InProcess timed out after {req.timeout}s")

        if isinstance(result, TransportResponse):
            return result
        return TransportResponse(status_code=0, body=str(result))

    async def stream(self, request: TransportRequest) -> AsyncIterator[TransportChunk]:
        """Execute and yield chunks from an async generator or iterable."""
        req = self._resolve_request(request)
        try:
            result = await asyncio.wait_for(
                self._execute(req),
                timeout=req.timeout,
            )
        except asyncio.TimeoutError:
            raise TransportError(0, f"InProcess stream timed out after {req.timeout}s")

        if isinstance(result, AsyncIterator):
            async for chunk in result:
                if isinstance(chunk, TransportChunk):
                    yield chunk
                else:
                    yield TransportChunk(data=str(chunk))
        elif hasattr(result, "__iter__"):
            for item in result:
                if isinstance(item, TransportChunk):
                    yield item
                else:
                    yield TransportChunk(data=str(item))
        else:
            yield TransportChunk(data=str(result), done=True)

    # ── Inbound ────────────────────────────────────────────

    async def serve(self, handler: Callable[[TransportRequest], Awaitable[TransportResponse]]) -> None:
        """In inbound mode, just store the handler.

        Unlike HTTP/CLI which need to LISTEN, InProcess "serving" means
        the callable IS the handler. So we swap:
            self.callable = handler
        and direction to INBOUND.
        """
        self._inbound_handler = handler
        self.callable = handler
        self._direction = Direction.INBOUND

    # ── Lifecycle ──────────────────────────────────────────

    async def close(self) -> None:
        self._callable = None
        self._inbound_handler = None
