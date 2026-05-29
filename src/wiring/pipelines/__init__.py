# wiring/pipelines/__init__.py
"""
Directional Communication Pipelines.
يُصدر الخطوط الواردة والصادرة كواجهات أوركستريشن موحدة تربط L3-L7.
جاهز للحقن في `ActorAssembler` أو `FastAPIRouter`.
"""
from __future__ import annotations

from .base import BaseCommunicationPipeline, PipelineExecutionError
from .outbound import OutboundCommunicationPipeline
from .inbound import InboundCommunicationPipeline

__all__ = [
    "BaseCommunicationPipeline",
    "PipelineExecutionError",
    "OutboundCommunicationPipeline",
    "InboundCommunicationPipeline",
]