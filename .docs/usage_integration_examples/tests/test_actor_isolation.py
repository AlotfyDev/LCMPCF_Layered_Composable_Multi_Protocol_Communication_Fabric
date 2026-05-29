# tests/test_actor_isolation.py
"""
Actor Isolation & Contract Compliance Test.
يُثبت أن BaseActor يعتمد حصريًا على ICommunicationGateway،
ويعمل بشكل معزول تمامًا عن الشبكة، البروتوكولات، أو السجلات الداخلية.
متوافق مع pytest-asyncio ويغطي حالات النجاح، الفشل، البث، والتنظيف الآمن.
"""
from __future__ import annotations

import asyncio
import pytest
from typing import Any, AsyncIterator, Dict, List, Optional

from actors.base_actor import BaseActor
from contracts.communication_gateway import ICommunicationGateway


# ─────────────────────────────────────────────────────────────
# 🔹 MockGateway (يطبق العقد صراحةً، ويُسجّل المكالمات للاختبار)
# ─────────────────────────────────────────────────────────────
class MockGateway(ICommunicationGateway):
    """بوابة وهمية للاختبار المعزول. تُسجّل التفاعلات وتُحاكي النجاح/الفشل/البث."""

    def __init__(self):
        self.send_calls: List[Dict[str, Any]] = []
        self.close_calls: List[Dict[str, Any]] = []
        self.stream_calls: List[Dict[str, Any]] = []
        self.mock_response: Any = {"status": "ok", "data": {"id": 1}}
        self.mock_stream_chunks: List[Any] = [{"step": 1, "content": "A"}, {"step": 2, "content": "B"}]
        self.should_fail: bool = False
        self.fail_message: str = "Simulated infrastructure failure"

    async def send(
        self, payload: Any, protocol: str = "http", session_id: Optional[str] = None,
        correlation_id: Optional[str] = None, stream: bool = False,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Any:
        self.send_calls.append({
            "payload": payload, "protocol": protocol, "session_id": session_id,
            "correlation_id": correlation_id, "stream": stream, "metadata": metadata
        })
        if self.should_fail:
            raise RuntimeError(self.fail_message)
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
        self.stream_calls.append({"protocol": protocol, "session_id": session_id, "metadata": metadata})
        for chunk in self.mock_stream_chunks:
            yield chunk

    async def close_session(self, session_id: str, protocol: str = "http") -> None:
        self.close_calls.append({"session_id": session_id, "protocol": protocol})

    async def health_check(self) -> Dict[str, Any]: return {"status": "healthy"}
    async def liveness_check(self) -> Dict[str, Any]: return {"status": "alive"}
    async def readiness_check(self) -> Dict[str, Any]: return {"status": "ready"}


# ─────────────────────────────────────────────────────────────
# 🔹 اختبارات العزل والامتثال للعقد
# ─────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_execute_task_success_and_cleanup():
    """يُثبت: نجاح المهمة، معالجة البيانات منطقيًا، وتنظيف الجلسة تلقائيًا."""
    gw = MockGateway()
    actor = BaseActor(gateway=gw, actor_id="isolated-actor")

    payload = {"action": "analyze", "target": "metrics.json"}
    result = await actor.execute_task(payload, protocol="http")

    assert result["status"] == "success"
    assert "_actor_processed" in result["data"]
    assert result["data"]["id"] == 1  # بيانات الـ Mock

    # ✅ إثبات العزل: الفابريك لم يُستدعَ، المكالمات سُجّلت محليًا
    assert len(gw.send_calls) == 1
    assert gw.send_calls[0]["payload"] == payload
    assert gw.send_calls[0]["protocol"] == "http"
    assert gw.send_calls[0]["metadata"]["actor_id"] == "isolated-actor"

    # ✅ إثبات إدارة دورة الحياة: الجلسة تُغلق دائمًا في finally
    assert len(gw.close_calls) == 1
    assert "isolated-actor-" in gw.close_calls[0]["session_id"]


@pytest.mark.asyncio
async def test_execute_task_failure_handling():
    """يُثبت: عزل الأخطاء، عدم تسرب الاستثناءات، واستمرار التنظيف الآمن."""
    gw = MockGateway()
    gw.should_fail = True
    actor = BaseActor(gateway=gw, actor_id="fail-actor")

    result = await actor.execute_task({"action": "fail"}, protocol="graphql")

    assert result["status"] == "error"
    assert gw.fail_message in result["message"]
    assert len(gw.close_calls) == 1  # ✅ التنظيف يحدث حتى عند الفشل


@pytest.mark.asyncio
async def test_stream_response_processing():
    """يُثبت: معالجة البث المتدفق chunk-by-chunk مع عزل كامل عن L4/L6."""
    gw = MockGateway()
    actor = BaseActor(gateway=gw, actor_id="stream-actor")

    chunks = []
    async for chunk in actor.stream_response("test_query", protocol="http"):
        chunks.append(chunk)

    assert len(chunks) == 2
    assert chunks[0]["chunk"] == {"step": 1, "content": "A"}
    assert chunks[0]["actor"] == "stream-actor"
    assert chunks[1]["session"].startswith("stream-actor-stream-")


@pytest.mark.asyncio
async def test_inbound_event_callback():
    """يُثبت: استقبال الأحداث الواردة ومعالجتها محليًا دون اتصال شبكي."""
    gw = MockGateway()
    received_events = []
    actor = BaseActor(
        gateway=gw, 
        actor_id="event-actor",
        on_event_callback=lambda e: received_events.append(e)
    )

    actor.handle_inbound_event({"type": "system_alert", "severity": "high"})
    assert len(received_events) == 1
    assert received_events[0]["type"] == "system_alert"


@pytest.mark.asyncio
async def test_multiple_sessions_isolation():
    """يُثبت: عدم تداخل الجلسات المتزامنة، كل واحدة لها معرّف فريد وتنظيف مستقل."""
    gw = MockGateway()
    actor = BaseActor(gateway=gw, actor_id="multi-actor")

    tasks = [
        actor.execute_task({"id": 1}, protocol="http"),
        actor.execute_task({"id": 2}, protocol="graphql"),
        actor.execute_task({"id": 3}, protocol="websocket"),
    ]
    await asyncio.gather(*tasks)

    assert len(gw.send_calls) == 3
    assert len(gw.close_calls) == 3
    session_ids = {c["session_id"] for c in gw.close_calls}
    assert len(session_ids) == 3  # ✅ لا تكرار، كل جلسة مستقلة


@pytest.mark.asyncio
async def test_gateway_contract_compliance():
    """يُثبت: أن الـ Mock يطبق ICommunicationGateway تمامًا، مما يضمن توافق البدائل الحقيقية."""
    gw = MockGateway()
    assert hasattr(gw, "send") and asyncio.iscoroutinefunction(gw.send)
    assert hasattr(gw, "close_session") and asyncio.iscoroutinefunction(gw.close_session)
    assert hasattr(gw, "health_check") and asyncio.iscoroutinefunction(gw.health_check)
    
    # التحقق من أن الفابريك الحقيقي والـ Mock يتشاركان نفس العقد البنيوي
    from contracts.communication_gateway import ICommunicationGateway
    assert isinstance(gw, ICommunicationGateway)
    
    
    
"""
🧪 كيف تشغّل الاختبار وتُثبت النتيجة؟
# 1. تثبيت المتطلبات
pip install pytest pytest-asyncio

# 2. تشغيل الاختبار
pytest tests/test_actor_isolation.py -v

# 3. الناتج المتوقع
# ✅ test_execute_task_success_and_cleanup PASSED
# ✅ test_execute_task_failure_handling PASSED
# ✅ test_stream_response_processing PASSED
# ✅ test_inbound_event_callback PASSED
# ✅ test_multiple_sessions_isolation PASSED
# ✅ test_gateway_contract_compliance PASSED



📐 ماذا يثبت هذا الاختبار معماريًا؟
المعيار
كيف يثبته الكود
DIP صريح
BaseActor لا يستورد FabricClient، ChannelPool، أو أي بنية تحتية. يعتمد فقط على ICommunicationGateway
عزل كامل
MockGateway لا يفتح مقابس، لا يتصل بشبكة، لا يدير جلسات حقيقية. الاختبار يعمل في 0ms
إدارة دورة حياة مضمونة
close_calls == send_calls حتى عند الفشل أو الاستثناءات، مما يثبت أن finally يعمل دائمًا
توافق العقد
isinstance(gw, ICommunicationGateway) يضمن أن أي بديل مستقبلي (FabricClient, RemoteAdapter, InMemoryBus) سيعمل دون تعديل كود الوكيل
عدم تداخل الجلسات
test_multiple_sessions_isolation يثبت أن المعرّفات فريدة، والتنظيف فردي، والبروتوكولات منفصلة


"""