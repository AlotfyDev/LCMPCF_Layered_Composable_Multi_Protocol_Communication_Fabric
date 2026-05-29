# presentation/codecs/compression.py
"""
OSI Layer 6 Compression Adapter (ICompressor Implementation).
مسؤوليته حصريًا: تطبيق خوارزميات ضغط مختلفة (Gzip, Zstd) تحت واجهة ICompressor الموحدة.
حالة صفرية (Stateless), آمن للأحداثية (Thread-Safe), ومحايد لاتجاه المعالجة.
يتوافق مع OSI L6: يقلل حجم تمثيل البيانات دون تغيير دلالتها.
"""
from __future__ import annotations

import gzip
import logging
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from presentation.protocol import ICompressor, PresentationError

logger = logging.getLogger(__name__)


class CompressionAlgorithm(str, Enum):
    GZIP = "gzip"
    ZSTD = "zstd"


class CompressionAdapter(ICompressor):
    """
    محول ضغط متعدد الخوارزميات (Gzip, Zstd).
    يتبع استراتيجية Lazy Import: يستورد Zstandard فقط عند استخدامه.
    """

    def __init__(
        self,
        algorithm: CompressionAlgorithm = CompressionAlgorithm.ZSTD,
        level: int = 3
    ):
        self.algorithm = algorithm
        self.level = level

    def compress(self, data: bytes) -> bytes:
        try:
            if self.algorithm == CompressionAlgorithm.GZIP:
                return gzip.compress(data, compresslevel=self.level)
            elif self.algorithm == CompressionAlgorithm.ZSTD:
                return self._zstd_compress(data)
            else:
                raise PresentationError(f"Unsupported compression algorithm: {self.algorithm}")
        except PresentationError:
            raise
        except Exception as e:
            raise PresentationError(f"Compression failed ({self.algorithm.value}): {e}") from e

    def decompress(self, data: bytes) -> bytes:
        try:
            if self.algorithm == CompressionAlgorithm.GZIP:
                return gzip.decompress(data)
            elif self.algorithm == CompressionAlgorithm.ZSTD:
                return self._zstd_decompress(data)
            else:
                raise PresentationError(f"Unsupported decompression algorithm: {self.algorithm}")
        except PresentationError:
            raise
        except Exception as e:
            raise PresentationError(
                f"Decompression failed ({self.algorithm.value}): {e}"
            ) from e

    # ── Zstd Lazy Imports ──────────────────────────────────────

    def _zstd_compress(self, data: bytes) -> bytes:
        try:
            import zstandard
            compressor = zstandard.ZstdCompressor(level=self.level)
            return compressor.compress(data)
        except ImportError:
            raise PresentationError(
                "Zstandard library is not installed. Install it with: pip install zstandard"
            ) from None

    def _zstd_decompress(self, data: bytes) -> bytes:
        try:
            import zstandard
            decompressor = zstandard.ZstdDecompressor()
            return decompressor.decompress(data)
        except ImportError:
            raise PresentationError(
                "Zstandard library is not installed. Install it with: pip install zstandard"
            ) from None
