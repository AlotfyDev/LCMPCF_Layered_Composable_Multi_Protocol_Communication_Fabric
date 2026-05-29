# presentation/codecs/__init__.py
"""
OSI Layer 6 Codecs Package (Internal Implementations).
يجمع المحولات التنفيذية للترجمة، ترميز التدفقات، والضغط.
يُستخدم داخليًا من قبل Pipeline، ويُصدّر اختياريًا للمستهلكين المتقدمين.
"""
from presentation.codecs.json_serializer import JsonSerializer
from presentation.codecs.sse_stream_codec import SSEStreamCodec
from presentation.codecs.compression import CompressionAdapter, CompressionAlgorithm

__all__ = [
    "JsonSerializer",
    "SSEStreamCodec",
    "CompressionAdapter",
    "CompressionAlgorithm",
]