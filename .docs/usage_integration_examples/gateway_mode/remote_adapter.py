# examples/gateway_mode/remote_adapter.py
"""
Remote Gateway Adapter.
يطبق ICommunicationGateway لكنه يستدعي نقاط نهاية FabricService عبر HTTP.
يُثبت أن الوكيل لا يحتاج معرفة بنمط النشر.
"""
from __future__ import annotations
import httpx
from typing import Any, AsyncIterator, Dict, Optional
from contracts.communication_gateway import ICommunicationGateway

class RemoteGatewayAdapter(ICommunicationGateway):
    def __init__(self, base_url: str = "http://localhost:8000/api/v1"):
        self._client = httpx.AsyncClient(base_url=base_url, timeout=30.0)

    async def send(self, payload: Any, protocol: str = "http", session_id: Optional[str] = None, correlation_id: Optional[str] = None, stream: bool = False, metadata: Optional[Dict[str, Any]] = None) -> Any:
        resp = await self._client.post("/send", json={
            "payload": payload, "protocol": protocol, "session_id": session_id,
            "correlation_id": correlation_id, "stream": stream, "metadata": metadata
        })
        resp.raise_for_status()
        return resp.json()

    async def receive(self, raw_bytes: bytes, protocol: str = "http", session_id: Optional[str] = None, metadata: Optional[Dict[str, str]] = None, channel_ref: Optional[str] = None) -> Any:
        # في النمط المركزي، الـ receive يُستدعى عادةً من الـ Adapter المحلي
        # لكن لدعم العقد، نحول البايتات إلى base64 ونرسلها للنقطة المناسبة
        import base64
        resp = await self._client.post("/receive", json={
            "raw_bytes": base64.b64encode(raw_bytes).decode(),
            "protocol": protocol, "session_id": session_id, "metadata": metadata
        })
        resp.raise_for_status()
        return resp.json()

    async def receive_stream(self, byte_stream: AsyncIterator[bytes], protocol: str = "http", session_id: Optional[str] = None, metadata: Optional[Dict[str, str]] = None) -> AsyncIterator[Any]:
        # محاكاة استدعاء SSE endpoint في الفابريك
        async with self._client.stream("POST", "/stream", json={
            "protocol": protocol, "session_id": session_id, "metadata": metadata
        }) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    import json
                    yield json.loads(line[6:])

    async def close_session(self, session_id: str, protocol: str = "http") -> None:
        await self._client.post("/close_session", json={"session_id": session_id, "protocol": protocol})

    async def health_check(self) -> Dict[str, Any]: return (await self._client.get("/health")).json()
    async def liveness_check(self) -> Dict[str, Any]: return (await self._client.get("/live")).json()
    async def readiness_check(self) -> Dict[str, Any]: return (await self._client.get("/ready")).json()

    async def close(self) -> None: await self._client.aclose()