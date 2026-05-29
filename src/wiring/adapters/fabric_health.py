# adapters/fabric_health.py
"""
Production Health Endpoints Adapter (/live, /ready, /health).
متوافق مع معايير Kubernetes, Docker, و AWS ALB Health Checks.
يعتمد حصريًا على ICommunicationGateway ولا يلامس التنفيذ الداخلي.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Tuple

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from contracts.communication_gateway import ICommunicationGateway

logger = logging.getLogger(__name__)

# خريطة تعيين حالات HTTP القياسية
_STATUS_MAP: Dict[str, int] = {
    "alive": status.HTTP_200_OK,
    "ready": status.HTTP_200_OK,
    "healthy": status.HTTP_200_OK,
    "not_ready": status.HTTP_503_SERVICE_UNAVAILABLE,
    "error": status.HTTP_500_INTERNAL_SERVER_ERROR,
    "unknown": status.HTTP_503_SERVICE_UNAVAILABLE,
}

class FabricHealthEndpoints:
    """مجمع نقاط فحص الصحة لواجهة FastAPI."""

    def __init__(self, gateway: ICommunicationGateway, prefix: str = ""):
        self.gateway = gateway
        self.router = APIRouter(prefix=prefix, tags=["Fabric Health & Lifecycle"])
        self._register_routes()

    def _register_routes(self) -> None:
        self.router.add_api_route("/live", self._live, methods=["GET"], summary="K8s Liveness Probe")
        self.router.add_api_route("/ready", self._ready, methods=["GET"], summary="K8s Readiness Probe")
        self.router.add_api_route("/health", self._health, methods=["GET"], summary="General System Health")

    async def _handle_probe(self, check_name: str, check_coro) -> JSONResponse:
        """منطق موحد للتعامل مع أي فحص صحة مع عزل الأخطاء وتعيين الحالة."""
        try:
            result: Dict[str, Any] = await check_coro()
            probe_status = result.get("status", "unknown")
            http_code = _STATUS_MAP.get(probe_status, status.HTTP_503_SERVICE_UNAVAILABLE)
            return JSONResponse(content=result, status_code=http_code)
        except Exception as e:
            logger.error(f"{check_name} probe failed: {e}", exc_info=True)
            return JSONResponse(
                content={"status": "error", "message": f"{check_name} check unavailable", "details": str(e)},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def _live(self) -> JSONResponse:
        return await self._handle_probe("Liveness", self.gateway.liveness_check)

    async def _ready(self) -> JSONResponse:
        return await self._handle_probe("Readiness", self.gateway.readiness_check)

    async def _health(self) -> JSONResponse:
        return await self._handle_probe("Health", self.gateway.health_check)