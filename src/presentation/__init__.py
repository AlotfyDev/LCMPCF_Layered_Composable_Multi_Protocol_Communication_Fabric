from __future__ import annotations
"""
OSI Layer 6 Presentation Layer (Public API).
مسؤولة حصريًا عن: Translation, Compression, Stream Framing.
توفر واجهة موحدة وآمنة للمستهلكين (L7 / BaseActor) دون كشف تفاصيل التنفيذ الداخلي.
تتوافق مع تعريف Cloudflare OSI L6 وتطبق مبدأ Dependency Inversion عبر العقود المجردة.
"""
from presentation.protocol import (
    ISerializer,
    IStreamCodec,
    ICompressor,
    PresentationError,
)
from presentation.pipeline import PresentationPipeline, PipelineConfig
from presentation.codecs import (
    JsonSerializer,
    SSEStreamCodec,
    CompressionAdapter,
    CompressionAlgorithm,
)

from .request_types import (
    CLIRequest,
    HTTPRequest,
    InProcessRequest,
    TransportChunk,
    TransportRequest,
    TransportResponse,
    gRPCRequest,
)
__all__ = [ # 📜 العقود المجردة (Contracts)
    "ISerializer",
    "IStreamCodec",
    "ICompressor",
    "PresentationError",
    
    # ⚙️ المنسق الاتجاهي (Orchestrator)
    "PresentationPipeline",
    "PipelineConfig",
    
    # 🛠️ التنفيذات الجاهزة (Codecs)
    "JsonSerializer",
    "SSEStreamCodec",
    "CompressionAdapter",
    "CompressionAlgorithm",
    "CLIRequest",
    "HTTPRequest",
    "InProcessRequest",
    "TransportChunk",
    "TransportRequest",
    "TransportResponse",
    "gRPCRequest",

]
