# presentation/codecs/json_serializer.py
"""
OSI Layer 6 JSON Serializer/Deserializer (Translation Codec).
مسؤوليته حصريًا: تحويل نماذج Pydantic التطبيقية ↔ تسلسل بايتات JSON (UTF-8).
يتوافق مع تعريف OSI L6 (Translation) ويطبق عقد ISerializer المجردة.
حالة صفرية (Stateless)، محايد للاتجاه، وقابل للحقن في PresentationPipeline.
"""
from __future__ import annotations

import json
from typing import Any, TypeVar
from pydantic import BaseModel, ValidationError

from presentation.protocol import ISerializer, PresentationError

# ربط النوعي بـ BaseModel لضمان سلامة التحقق الثابت والديناميكي
T = TypeVar("T", bound=BaseModel)


class JsonSerializer(ISerializer[T]):
    """
    مُحوّل JSON لنماذج بايثون التطبيقية (OSI L6 Translation).
    يحوّل الكائنات إلى تنسيق سلكي (Wire Format) والعكس، مع ضمان صحة المخطط.
    """

    def __init__(
        self,
        ensure_ascii: bool = False,
        by_alias: bool = False,
        exclude_unset: bool = False,
        exclude_none: bool = True
    ):
        """
        يهيئ محوّل JSON بخيارات ترميز قابلة للتخصيص.
        
        Args:
            ensure_ascii: إذا True، يهرب الأحرف غير ASCII (مفيد للأنظمة القديمة)
            by_alias: إذا True، يستخدم أسماء الحقول المُعرفة في Field(alias=...)
            exclude_unset: إذا True، يستبعد الحقول التي لم تُعيّن صراحةً
            exclude_none: إذا True، يستبعد الحقول ذات القيمة None لتقليل الحجم
        """
        self._ensure_ascii = ensure_ascii
        self._by_alias = by_alias
        self._exclude_unset = exclude_unset
        self._exclude_none = exclude_none

    def serialize(self, obj: T) -> bytes:
        """
        يحوّل كائن Pydantic إلى بايتات JSON UTF-8 جاهزة للنقل.
        
        Raises:
            PresentationError: إذا لم يكن الكائن من نوع BaseModel أو فشل الترميز
        """
        if not isinstance(obj, BaseModel):
            raise PresentationError(
                f"JsonSerializer requires a Pydantic BaseModel, got {type(obj).__name__}"
            )
        try:
            # Pydantic v2 optimized serialization → UTF-8 bytes
            json_str = obj.model_dump_json(
                ensure_ascii=self._ensure_ascii,
                by_alias=self._by_alias,
                exclude_unset=self._exclude_unset,
                exclude_none=self._exclude_none,
            )
            return json_str.encode("utf-8")
        except Exception as e:
            raise PresentationError(f"Serialization to JSON failed: {e}") from e

    def deserialize(self, data: bytes, target_type: type[T] | None = None) -> T:
        """
        يفك تشفير بايتات JSON ويعيدها إلى كائن Pydantic مُتحقق من صحته.
        
        Args:
            data: بايتات JSON خام
            target_type: فئة Pydantic المستهدفة (إلزامي للاستدلال الصحيح)
            
        Raises:
            PresentationError: إذا كانت البيانات غير صالحة، أو فشل التحقق من المخطط
        """
        if target_type is None:
            raise PresentationError("target_type is required for safe deserialization")
        if not issubclass(target_type, BaseModel):
            raise PresentationError(
                f"target_type must inherit from BaseModel, got {target_type}"
            )

        try:
            # Pydantic v2 optimized validation from bytes
            return target_type.model_validate_json(data)
        except ValidationError as e:
            raise PresentationError(
                f"JSON schema validation failed for {target_type.__name__}: {e}"
            ) from e
        except json.JSONDecodeError as e:
            raise PresentationError(f"Invalid JSON byte stream: {e}") from e
        except Exception as e:
            raise PresentationError(
                f"Deserialization to {target_type.__name__} failed: {e}"
            ) from e