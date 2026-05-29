# presentation/pipeline.py
"""
OSI Layer 6 Presentation Pipeline (Directional Orchestrator).
مسؤوليته حصريًا: ترتيب مكونات الترجمة والضغط بناءً على الاتجاه، 
تطبيق تجاوز (Bypass) للعمليات المحلية، وفرض عتبات ضغط ذكية.
يتوافق مع تعريف OSI L6: translation, compression, (charset normalization).
لا يخزن حالة، لا يفسر بروتوكول نقل، ويعزل منطق التنسيق عن تنفيذ المحولات.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional, TypeVar

from pydantic import BaseModel, Field, ConfigDict
from transport.base import Direction
from presentation.protocol import ISerializer, IStreamCodec, ICompressor, PresentationError

logger = logging.getLogger(__name__)
T = TypeVar("T")


@dataclass(frozen=True)
class PipelineConfig:
    """
    تكوين خط العرض (L6 Pipeline Configuration).
    يُمرر عند التهيئة ولا يتغير أثناء التشغيل (Immutability for Thread-Safety).
    """
    min_compression_bytes: int = Field(default=1024, ge=0, description="الحد الأدنى للحمولة لتفعيل الضغط (بايت)")
    charset: str = Field(default="utf-8", description="ترميز النص الافتراضي للتحويل الثنائي")
    auto_detect_compression: bool = Field(default=True, description="كشف سحري لبيانات مضغوطة عند الاستلام")


class PresentationPipeline:
    """
    منسق خط العرض (OSI L6 Orchestrator).
    يرتب: Object -> Serialize -> [Compress] -> Bytes (Outbound)
           Bytes -> [Decompress] -> Deserialize -> Object (Inbound)
    يتجاوز المعالجة كليًا عند INPROCESS أو عند عدم توفر مكونات.
    """

    # رؤوس سحرية لكشف الضغط تلقائيًا (Magic Bytes)
    _MAGIC_GZIP = b"\x1f\x8b"
    _MAGIC_ZSTD = b"\x28\xb5\x2f\xfd"

    def __init__(
        self,
        direction: Direction,
        serializer: Optional[ISerializer[Any]] = None,
        stream_codec: Optional[IStreamCodec] = None,
        compressor: Optional[ICompressor] = None,
        config: Optional[PipelineConfig] = None
    ):
        self.direction = direction
        self.serializer = serializer
        self.stream_codec = stream_codec
        self.compressor = compressor
        self.config = config or PipelineConfig()
        
        # تحقق منطقي عند التهيئة
        if self._is_bypass() and not (self.serializer or self.stream_codec):
            logger.debug("PresentationPipeline initialized in BYPASS mode (INPROCESS or no components)")

    def _is_bypass(self) -> bool:
        """يقرر ما إذا كان يجب تجاوز المعالجة كليًا."""
        is_local = self.direction == Direction.INPROCESS
        no_components = not (self.serializer or self.stream_codec or self.compressor)
        return is_local or no_components

    def _should_compress(self, data: bytes) -> bool:
        """يقرر تفعيل الضغط بناءً على الحجم والإعدادات."""
        if not self.compressor or not self.config.auto_detect_compression:
            return False
        return len(data) >= self.config.min_compression_bytes

    def _is_compressed(self, data: bytes) -> bool:
        """يكشف تلقائيًا إذا كانت البيانات مضغوطة عبر الرؤوس السحرية."""
        if not self.config.auto_detect_compression or len(data) < 4:
            return False
        return data.startswith(self._MAGIC_GZIP) or data.startswith(self._MAGIC_ZSTD)

    # ── Sync Encode / Decode (Message-Level) ──────────────────

    def encode(self, obj: Any) -> bytes:
        """
        OUTBOUND: Object -> Serialize -> [Compress] -> Bytes
        يتجاوز التحويل عند INPROCESS.
        """
        if self._is_bypass():
            if isinstance(obj, bytes):
                return obj
            raise PresentationError("Bypass mode requires bytes input. Provide a serializer or use INBOUND direction.")

        if not self.serializer:
            raise PresentationError("Serializer is required for OUTBOUND encoding")

        try:
            # 1. الترجمة (Translation)
            data = self.serializer.serialize(obj)
            
            # 2. الضغط الشرطي (Conditional Compression)
            if self.compressor and self._should_compress(data):
                data = self.compressor.compress(data)
                logger.debug(f"Pipeline compressed payload: {len(data)} bytes ({self.compressor.__class__.__name__})")
                
            return data
        except PresentationError:
            raise
        except Exception as e:
            raise PresentationError(f"Pipeline encode failed: {e}") from e

    def decode(self, data: bytes, target_type: type[T]) -> T:
        """
        INBOUND: Bytes -> [Decompress] -> Deserialize -> Object
        يتجاوز التحويل عند INPROCESS.
        """
        if self._is_bypass():
            raise PresentationError("Bypass mode does not support decoding. Provide a serializer or use OUTBOUND direction.")

        if not self.serializer:
            raise PresentationError("Serializer is required for INBOUND decoding")

        try:
            # 1. فك الضغط التلقائي أو القسري
            if self.compressor and (self._is_compressed(data) or self.config.min_compression_bytes == 0):
                data = self.compressor.decompress(data)
                logger.debug("Pipeline auto-decompressed payload")
                
            # 2. الترجمة العكسية (Reverse Translation)
            return self.serializer.deserialize(data, target_type)
        except PresentationError:
            raise
        except Exception as e:
            raise PresentationError(f"Pipeline decode failed: {e}") from e

    # ── Async Stream Encode / Decode (Frame-Level) ────────────

    async def encode_stream(self, obj_stream: AsyncIterator[Any]) -> AsyncIterator[bytes]:
        """يحوّل تدفق كائنات إلى تدفق بايتات مع ضغط/ترميز شرطي."""
        if self._is_bypass():
            async for chunk in obj_stream:
                yield chunk if isinstance(chunk, bytes) else chunk.encode(self.config.charset)
            return

        if not self.stream_codec and not self.serializer:
            raise PresentationError("StreamCodec or Serializer is required for stream encoding")

        codec = self.stream_codec
        async for obj in obj_stream:
            try:
                # ترجمة أولية إذا لم يكن StreamCodec موجودًا
                raw = self.serializer.serialize(obj) if self.serializer and not codec else obj
                
                # ترميز التدفق
                if codec:
                    async for frame in codec.encode_stream(self._single_item_stream(raw)):
                        yield frame
                else:
                    yield raw
            except Exception as e:
                raise PresentationError(f"Pipeline stream encode failed: {e}") from e

    async def decode_stream(self, byte_stream: AsyncIterator[bytes]) -> AsyncIterator[Any]:
        """يفك ترميز تدفق بايتات ويعيده كدفق كائنات."""
        if self._is_bypass():
            async for chunk in byte_stream:
                yield chunk
            return

        if not self.stream_codec and not self.serializer:
            raise PresentationError("StreamCodec or Serializer is required for stream decoding")

        codec = self.stream_codec
        async for frame in byte_stream:
            try:
                # فك ضغط تلقائي للإطارات
                data = self.compressor.decompress(frame) if self.compressor and self._is_compressed(frame) else frame
                
                if codec:
                    async for obj in codec.decode_stream(self._single_item_stream(data)):
                        yield obj
                elif self.serializer:
                    yield self.serializer.deserialize(data, target_type=Any)  # Any fallback
            except Exception as e:
                raise PresentationError(f"Pipeline stream decode failed: {e}") from e

    # ── Helpers ───────────────────────────────────────────────

    @staticmethod
    async def _single_item_stream(item: Any) -> AsyncIterator[Any]:
        """غلاف لتحويل عنصر مفرد إلى AsyncIterator متوافق مع StreamCodec."""
        yield item

    # ── Context Manager Support (اختياري للإغلاق الآمن مستقبلاً) ──
    async def __aenter__(self) -> PresentationPipeline:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        pass  # Stateless pipeline requires no cleanup
