# wiring/registry/pipeline_registry.py
"""
Directional Pipeline Registry (Indexing & Routing).
مسؤوليته حصريًا: تخزين، فهرسة، واسترجاع خطوط المعالجة الاتجاهية (Inbound/Outbound)
بناءً على مفتاح مركب (direction, protocol). يمكّن التبديل الحي، التوجيه الديناميكي،
والعزل الكامل لدورات حياة الخطوط المتعددة.

✅ Composite Key Indexing: (direction, protocol) → Pipeline
✅ Async-Safe & Non-Blocking
✅ Metadata Tracking: يسجل وقت الإنشاء، الإصدار، وحالة التشغيل
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from wiring.pipelines.base import BaseCommunicationPipeline

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineMetadata:
    """بيانات وصفية لخط معالجة مسجل."""
    direction: str
    protocol: str
    registered_at: float
    component_type: str


class PipelineRegistry:
    """سجل فهرسة وتوجيه خطوط المعالجة الاتجاهية."""

    def __init__(self):
        self._index: Dict[Tuple[str, str], BaseCommunicationPipeline] = {}
        self._metadata: Dict[Tuple[str, str], PipelineMetadata] = {}
        self._lock = asyncio.Lock()
        self._closed = False

    # ── Registration & Retrieval ─────────────────────────────

    async def register(
        self,
        direction: str,
        protocol: str,
        pipeline: BaseCommunicationPipeline
    ) -> None:
        """يسجل خط معالجة اتجاهي جديد مع بيانات وصفية تلقائية."""
        async with self._lock:
            if self._closed:
                raise RuntimeError("Cannot register pipelines: registry is closed")
            key = (direction.lower(), protocol.lower())
            if key in self._index:
                logger.warning(f"Overwriting existing pipeline: {direction}/{protocol}")
                await self._index[key].close() if hasattr(self._index[key], "close") else None

            self._index[key] = pipeline
            self._metadata[key] = PipelineMetadata(
                direction=direction,
                protocol=protocol,
                registered_at=time.time(),
                component_type=pipeline.__class__.__name__
            )
            logger.info(f"Pipeline registered: {direction}/{protocol} -> {pipeline.__class__.__name__}")

    async def get(self, direction: str, protocol: str) -> Optional[BaseCommunicationPipeline]:
        """يسترجع خط معالجة حسب الاتجاه والبروتوكول."""
        async with self._lock:
            return self._index.get((direction.lower(), protocol.lower()))

    async def list_all(self) -> List[PipelineMetadata]:
        """يعيد قائمة بجميع الخطوط المسجلة مع بياناتها الوصفية."""
        async with self._lock:
            return list(self._metadata.values())

    # ── Lifecycle & Cleanup ──────────────────────────────────

    async def close(self) -> None:
        """يغلق جميع الخطوط المسجلة وينظّف السجل."""
        async with self._lock:
            self._closed = True
            pipelines = list(self._index.values())
            self._index.clear()
            self._metadata.clear()

        for pipe in pipelines:
            if hasattr(pipe, "close"):
                try:
                    await pipe.close()
                except Exception as e:
                    logger.error(f"Failed to close pipeline {pipe.__class__.__name__}: {e}")
        
        logger.info("PipelineRegistry closed and all pipelines finalized")

    async def get_stats(self) -> Dict[str, Any]:
        """يعيد إحصائيات سريعة عن السجل (للمراقبة والـ Health Checks)."""
        async with self._lock:
            return {
                "total_pipelines": len(self._index),
                "pipelines": [
                    {
                        "direction": m.direction,
                        "protocol": m.protocol,
                        "type": m.component_type,
                        "registered_at": m.registered_at
                    }
                    for m in self._metadata.values()
                ]
            }