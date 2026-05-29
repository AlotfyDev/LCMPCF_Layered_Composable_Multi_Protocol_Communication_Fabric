from __future__ import annotations

import logging
from typing import Optional

from transport.base import Direction
from presentation.pipeline import PresentationPipeline, PipelineConfig
from presentation.protocol import ISerializer, IStreamCodec, ICompressor
from presentation.codecs.json_serializer import JsonSerializer
from presentation.codecs.sse_stream_codec import SSEStreamCodec
from presentation.codecs.compression import CompressionAdapter

logger = logging.getLogger(__name__)


def build_serializer(serializer_name: str = "json") -> Optional[ISerializer]:
    """يبني المسلسل حسب الاسم."""
    if serializer_name == "json":
        return JsonSerializer()
    logger.warning(f"Unknown serializer '{serializer_name}', using JSON")
    return JsonSerializer()


def build_compressor(compressor_name: str = "gzip") -> Optional[ICompressor]:
    """يبني أداة الضغط حسب الاسم."""
    try:
        return CompressionAdapter(method=compressor_name)
    except Exception as e:
        logger.warning(f"Compressor '{compressor_name}' not available: {e}")
        return None


def build_stream_codec(codec_name: str = "sse") -> Optional[IStreamCodec]:
    """يبني مرمز التدفق حسب الاسم."""
    if codec_name == "sse":
        return SSEStreamCodec()
    logger.warning(f"Unknown stream codec '{codec_name}' — no codec configured")
    return None


def build_presentation_pipeline(
    direction: Direction,
    serializer_name: str = "json",
    compressor_name: str = "gzip",
    min_compression_bytes: int = 1024,
    auto_detect: bool = True,
    bypass_inprocess: bool = True,
) -> PresentationPipeline:
    """يبني خط عرض L6 متكامل مع جميع المكونات الاختيارية.

    Args:
        direction: اتجاه الخط (OUTBOUND لترميز، INBOUND لفك)
        serializer_name: اسم المسلسل (json, msgpack)
        compressor_name: اسم الضاغط (gzip, zstd, none)
        min_compression_bytes: أدنى حجم للتفعيل التلقائي للضغط
        auto_detect: كشف تلقائي للبيانات المضغوطة
        bypass_inprocess: تجاوز كامل للمعالجة في وضع INPROCESS

    Returns:
        PresentationPipeline جاهز للحقن.
    """
    serializer = build_serializer(serializer_name) if serializer_name != "none" else None
    compressor = build_compressor(compressor_name) if compressor_name != "none" else None

    pipeline = PresentationPipeline(
        direction=direction,
        serializer=serializer,
        compressor=compressor,
        config=PipelineConfig(
            min_compression_bytes=min_compression_bytes,
            auto_detect_compression=auto_detect,
        ),
    )

    if bypass_inprocess and direction == Direction.INPROCESS:
        logger.debug("PresentationPipeline: INPROCESS direction, bypass optimized")
    else:
        logger.info(
            f"PresentationPipeline built: dir={direction.value}, "
            f"serializer={serializer_name}, compressor={compressor_name}"
        )

    return pipeline
