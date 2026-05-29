# wiring/registry/layer_registry.py
"""
Layer Component Registry (Dependency Aggregator).
مسؤوليته حصريًا: تخزين، فهرسة، واسترجاع المكونات الأساسية لكل طبقة (L3-L7).
يضمن عزل التبعيات، يمنع التسريب بين الطبقات، ويوفر نقطة وصول موحدة لـ Assembler.

✅ Async-Safe: جميع العمليات محمية بـ asyncio.Lock
✅ Lifecycle-Aware: يدعم الإغلاق الآلي للمكونات القابلة للتنظيف
✅ Typed Accessors: واجهات وصول واضحة لكل طبقة لمنع الأخطاء النصية
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class RegistryError(Exception):
    """يُرفع عند محاولة الوصول لمكون غير مسجل أو السجل مغلق."""
    pass


class LayerRegistry:
    """سجل مركزي لتجميع المكونات الطبقية وإدارتها دورة حياتها."""

    def __init__(self):
        self._store: Dict[str, Any] = {}
        self._lock = asyncio.Lock()
        self._closed = False

    # ── Core Registration & Retrieval ────────────────────────

    async def register(self, layer: str, key: str, component: Any) -> None:
        """يسجل مكونًا جديدًا في السجل تحت مفتاح طبقي واضح."""
        async with self._lock:
            if self._closed:
                raise RegistryError("Cannot register components: registry is closed")
            qualified_key = f"{layer}.{key}"
            if qualified_key in self._store:
                logger.warning(f"Overwriting existing component: {qualified_key}")
            self._store[qualified_key] = component
            logger.debug(f"Component registered: {qualified_key}")

    async def get(self, layer: str, key: str, strict: bool = True) -> Optional[Any]:
        """يسترجع مكونًا مسجلًا. يرفع خطأ إذا لم يُوجد و strict=True."""
        async with self._lock:
            comp = self._store.get(f"{layer}.{key}")
        if comp is None and strict:
            raise RegistryError(f"Component not found: {layer}.{key}")
        return comp

    # ── Layer-Specific Typed Accessors ───────────────────────

    async def get_network_pool(self) -> Any:
        return await self.get("network", "channel_pool")

    async def get_session_dispatcher(self) -> Any:
        return await self.get("session", "dispatcher")

    async def get_session_registry(self) -> Any:
        return await self.get("session", "registry")

    async def get_presentation_pipeline(self) -> Any:
        return await self.get("presentation", "pipeline")

    async def get_protocol_handler(self, protocol: str) -> Any:
        return await self.get("protocol", protocol)

    # ── Lifecycle & Cleanup ──────────────────────────────────

    async def close(self) -> None:
        """يغلق السجل ويُنظّف جميع المكونات القابلة للإغلاق بالترتيب العكسي للتسجيل."""
        async with self._lock:
            self._closed = True
            components = list(self._store.values())
            self._store.clear()

        # إغلاق عكسي لضمان عدم اعتماد مكون على آخر مُغلق مسبقًا
        for comp in reversed(components):
            if hasattr(comp, "close") and asyncio.iscoroutinefunction(comp.close):
                try:
                    await comp.close()
                except Exception as e:
                    logger.error(f"Failed to close component {comp.__class__.__name__}: {e}")
            elif hasattr(comp, "close"):
                try:
                    comp.close()
                except Exception as e:
                    logger.error(f"Failed to close sync component {comp.__class__.__name__}: {e}")
        
        logger.info("LayerRegistry closed and all components finalized")

    async def list_registered(self) -> Dict[str, str]:
        """يعيد قائمة المكونات المسجلة للمراقبة والتصحيح."""
        async with self._lock:
            return {k: type(v).__name__ for k, v in self._store.items()}