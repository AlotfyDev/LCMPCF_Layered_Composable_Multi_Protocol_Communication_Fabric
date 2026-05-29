# transport/context/transport_context.py
"""
TransportContext: وعاء شفاف لحالة الجلسة يُمرر عبر L4 دون تفسير أو تعديل.
يمثل البيانات التي تحتاجها L5 لإدارة الحوار، تتبع الدفقات، واستئناف نقاط التفتيش.
"""
from typing import Any, Dict
from pydantic import BaseModel, Field, ConfigDict, field_validator

class TransportContext(BaseModel):
    """
    سياق النقل المُغلّف ببيانات الجلسة.
    ✅ Pydantic Validation: 
       - `frozen=True`: يمنع التعديل العرضي أثناء النقل المتزامن.
       - `extra='forbid'`: يرفض أي حقول غير معروفة للحفاظ على استقرار العقد.
       - `min_length`, `ge`: ضمان صحة المعرفات والإزاحات قبل التسليم.
    📦 Serialization: متوافق تلقائيًا مع JSON/MessagePack عبر model_dump()/model_validate()
    """
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        json_schema_extra={"description": "OSI L5 session state carried transparently by L4"}
    )

    session_id: str = Field(
        ..., 
        min_length=1, 
        max_length=128,
        description="معرف الجلسة المنطقي (L5 Session ID). يعامل كسلسلة معتمة من قبل L4."
    )
    correlation_id: str = Field(
        ..., 
        min_length=1, 
        max_length=128,
        description="معرف تتبع الطلب/الدفعة. يربط الرد بالطلب الأصلي عبر الطبقات."
    )
    stream_offset: int = Field(
        default=0, 
        ge=0,
        description="موقع الاستئناف في الدفق (بايت أو رسالة). يُحدثه L5 عند نقاط التفتيش."
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="وسوم إضافية محايدة (مؤشرات أداء، وسوم تتبع، إلخ). لا يُفسر من قبل L4."
    )

    @field_validator("session_id", "correlation_id")
    @classmethod
    def _validate_ids(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("معرفات الجلسة والترابط لا يمكن أن تكون فارغة أو تحتوي على مسافات فقط")
        return stripped

    @field_validator("metadata")
    @classmethod
    def _validate_metadata(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        # ضمان أن المفاتيح سلاسل نصية قصيرة لتجنب تضخم الهيدر/البيئة
        for key in v.keys():
            if not isinstance(key, str) or len(key) > 64:
                raise ValueError("مفاتيح البيانات الوصفية يجب أن تكون سلاسل نصية <= 64 حرف")
        return v