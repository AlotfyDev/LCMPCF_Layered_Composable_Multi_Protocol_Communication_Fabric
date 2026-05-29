# tests/conftest.py
"""
Global Test Configuration & Shared Fixtures.
يُوفر موارد معاد استخدامها عبر جميع ملفات الاختبار، ويقلل التكرار بشكل جذري.
متوافق مع pytest-asyncio و Clean Architecture Testing Patterns.
"""
from __future__ import annotations

import asyncio
import pytest
from typing import Any, AsyncIterator, Dict, List, Optional

from actors.base_actor import BaseActor
from contracts.communication_gateway import ICommunicationGateway


# ─────────────────────────────────────────────────────────────
# 🔹 MockGateway (Global Reusable Implementation)
# ─────────────────────────────────────────────────────────────
class MockGateway(ICommunicationGateway):
    """بوابة وهمية قياسية للاختبار المعزول. قابلة للتكوين ديناميكيًا."""

    def __init__(self):
        self.send_calls: List[Dict[str, Any]] = []
        self.close_calls: List[Dict[str, Any]] = []
        self.stream_calls: List[Dict[str, Any]] = []
        self.mock_response: Any = {"status": "ok", "data": {"mocked": True}}
        self.mock_stream_chunks: List[Any] = [{"step": 1}, {"step": 2}]
        self.raise_on_send: Optional[Exception] = None

    async def send(
        self, payload: Any, protocol: str = "http", session_id: Optional[str] = None,
        correlation_id: Optional[str] = None, stream: bool = False,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Any:
        self.send_calls.append({
            "payload": payload, "protocol": protocol, "session_id": session_id,
            "correlation_id": correlation_id, "stream": stream, "metadata": metadata
        })
        if self.raise_on_send:
            raise self.raise_on_send
        return self.mock_response

    async def receive(
        self, raw_bytes: bytes, protocol: str = "http", session_id: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None, channel_ref: Optional[str] = None
    ) -> Any:
        return {"received": True, "protocol": protocol}

    async def receive_stream(
        self, byte_stream: AsyncIterator[bytes], protocol: str = "http",
        session_id: Optional[str] = None, metadata: Optional[Dict[str, str]] = None
    ) -> AsyncIterator[Any]:
        self.stream_calls.append({"protocol": protocol, "session_id": session_id})
        for chunk in self.mock_stream_chunks:
            yield chunk

    async def close_session(self, session_id: str, protocol: str = "http") -> None:
        self.close_calls.append({"session_id": session_id, "protocol": protocol})

    async def health_check(self) -> Dict[str, Any]: return {"status": "healthy"}
    async def liveness_check(self) -> Dict[str, Any]: return {"status": "alive"}
    async def readiness_check(self) -> Dict[str, Any]: return {"status": "ready"}


# ─────────────────────────────────────────────────────────────
# 🔹 Pytest Fixtures
# ─────────────────────────────────────────────────────────────
@pytest.fixture
def mock_gateway() -> MockGateway:
    """يعيد نسخة جديدة ونظيفة من البوابة الوهمية لكل اختبار."""
    return MockGateway()


@pytest.fixture
def isolated_actor(mock_gateway: MockGateway) -> BaseActor:
    """يُنشئ وكيلًا معزولًا يعتمد فقط على العقد، جاهز للاختبار الفوري."""
    return BaseActor(
        gateway=mock_gateway,
        actor_id="test-actor",
        on_event_callback=lambda e: None
    )


@pytest.fixture(scope="session")
def event_loop():
    """يُضبط حلقة أحداث متوافقة مع نطاق الجلسة لاختبارات التكامل."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()