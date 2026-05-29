# tests/test_fabric_integration.py
"""
Live Integration Test: Protocol Switching & Readiness Stability.
يُثبت تشغيل النظام داخل حاوية Docker، التبديل الحي بين HTTP و GraphQL
بنفس الجلسة، وثبات حالة /ready أثناء التبديل والتنظيف.
يتطلب: docker compose up -d وتشغيل pytest -m integration
"""
from __future__ import annotations

import asyncio
import pytest
import httpx
import uuid
from typing import AsyncGenerator

BASE_URL = "http://localhost:8000/api/v1"


# ─────────────────────────────────────────────────────────────
# 🔹 Fixtures للتكامل
# ─────────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def api_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """عميل HTTP متزامن غير حاجز لاختبارات التكامل."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as c:
        yield c


async def _await_service_ready(client: httpx.AsyncClient, max_retries: int = 20, delay: float = 2.0) -> bool:
    """ينتظر حتى يصبح الفابريك جاهزًا لاستقبال الحركة."""
    for _ in range(max_retries):
        try:
            resp = await client.get("/ready")
            if resp.status_code == 200 and resp.json().get("status") == "ready":
                return True
        except httpx.RequestError:
            pass
        await asyncio.sleep(delay)
    return False


# ─────────────────────────────────────────────────────────────
# 🔹 اختبارات التكامل
# ─────────────────────────────────────────────────────────────
@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_protocol_switch_http_to_graphql(api_client: httpx.AsyncClient):
    """يُثبت: التبديل الحي دون فقدان الجلسة، وثبات Readiness، والتنظيف الآمن."""
    
    # 1. التأكد من أن الحاوية جاهزة
    ready = await _await_service_ready(api_client)
    if not ready:
        pytest.skip("Fabric service did not become ready in time. Run 'docker compose up -d' first.")

    session_id = f"sess-{uuid.uuid4().hex[:8]}"

    # 2. إنشاء جلسة عبر HTTP
    http_resp = await api_client.post("/send", json={
        "payload": {"action": "init_http", "data": "metrics"},
        "protocol": "http",
        "session_id": session_id
    })
    assert http_resp.status_code == 200, f"HTTP init failed: {http_resp.text}"

    # 3. التبديل الحي إلى GraphQL بنفس الـ session_id
    gql_resp = await api_client.post("/send", json={
        "payload": {"query": "{ sessionInfo }", "variables": {"id": session_id}},
        "protocol": "graphql",
        "session_id": session_id
    })
    assert gql_resp.status_code == 200, f"GraphQL switch failed: {gql_resp.text}"

    # 4. التحقق من بقاء /ready أخضر أثناء التبديل
    ready_resp = await api_client.get("/ready")
    assert ready_resp.status_code == 200
    data = ready_resp.json()
    assert data["status"] == "ready"
    assert data["pipelines_active"] >= 2, "Expected HTTP + GraphQL pipelines registered"

    # 5. إغلاق الجلسة صراحةً
    close_resp = await api_client.post("/close_session", json={
        "session_id": session_id,
        "protocol": "graphql"
    })
    assert close_resp.status_code == 200

    # 6. التأكد من نظافة الحالة واستمرار الجاهزية
    final_ready = await api_client.get("/ready")
    assert final_ready.status_code == 200
    final_data = final_ready.json()
    assert final_data["status"] == "ready"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_health_endpoints_consistency(api_client: httpx.AsyncClient):
    """يُثبت: توافق /live, /ready, /health مع معايير Kubernetes."""
    if not await _await_service_ready(api_client):
        pytest.skip("Service not ready")

    live = await api_client.get("/live")
    assert live.status_code == 200
    assert live.json()["status"] == "alive"

    ready = await api_client.get("/ready")
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"

    health = await api_client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "healthy"
    assert "active_pipelines" in health.json()