# wiring/registry/__init__.py
"""
Fabric Registries (Indexing & Aggregation).
يوفر واجهة موحدة لتجميع المكونات الطبقية وفهرسة خطوط المعالجة الاتجاهية.
جاهز للدمج المباشر مع ActorAssembler و Hot-Reload Config.
"""
from __future__ import annotations

from .layer_registry import LayerRegistry, RegistryError
from .pipeline_registry import PipelineRegistry, PipelineMetadata

__all__ = [
    "LayerRegistry",
    "RegistryError",
    "PipelineRegistry",
    "PipelineMetadata",
]