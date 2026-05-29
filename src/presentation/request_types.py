# presentation/request_types.py
"""
OSI Layer 7 Application Data Contracts (L6 Serialization Targets).
مسؤولة حصريًا عن: تعريف هياكل البيانات التطبيقية التي تستهلكها وتنتجها طبقة العرض (L6).

✅ تمت إزالة إعدادات النقل (timeout, retries, retry_delay) → تنتمي حصريًا لـ L4/L5 Config.
✅ تم تعميم `body` و `data` إلى `Any` لتمكين `JsonSerializer` و `SSEStreamCodec` من معالجتها ديناميكيًا.
✅ تم إزالة `TransportError` لتجنب التعارض مع `transport.base.TransportError` و `presentation.protocol.PresentationError`.
✅ متوافقة 100% مع Pydantic v2 وقابلة للتسلسل/التحقق عبر L6 Pipeline.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class TransportRequest(BaseModel):
    """عقد طلب تطبيقية أساسية. خالية من منطق النقل أو重试 السياسات."""
    model_config = ConfigDict(extra="allow")
    correlation_id: Optional[str] = Field(default=None, description="معرف تتبع الطلب عبر الطبقات")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="وسوم تطبيقية محايدة")


class HTTPRequest(TransportRequest):
    """طلب مخصص لسياق HTTP/A2A. `payload` يُسلسل تلقائيًا عبر L6."""
    url: str = Field(default="", description="عنوان المورد المستهدف")
    method: Literal["GET", "POST", "PUT", "DELETE", "PATCH"] = Field(default="POST")
    headers: Dict[str, str] = Field(default_factory=dict)
    payload: Any = Field(default=None, description="حمولة الطلب (dict, BaseModel, أو bytes)")


class CLIRequest(TransportRequest):
    """طلب مخصص لسياق Subprocess/CLI. يُمرر كـ JSON عبر stdin."""
    command: list[str] = Field(default_factory=list)
    stdin_data: Optional[str] = Field(default=None)
    cwd: Optional[str] = Field(default=None)
    env_overrides: Dict[str, str] = Field(default_factory=dict)


class InProcessRequest(TransportRequest):
    """طلب مخصص للاستدعاء المباشر داخل الذاكرة. `target` مُستبعد من التسلسل."""
    target: Optional[Callable] = Field(default=None, exclude=True, description="يُستبعد من التسلسل (L7 Runtime)")
    args: tuple = Field(default_factory=tuple)
    kwargs: Dict[str, Any] = Field(default_factory=dict)
    yield_mode: Optional[Literal["sync", "async"]] = Field(default="sync")


class gRPCRequest(TransportRequest):
    """طلب مخصص لسياق gRPC. `payload` يُحوّل لـ Protobuf عبر L6 codec مستقبليًا."""
    service: str = Field(default="", description="خدمة gRPC المستهدفة")
    method: str = Field(default="", description="طريقة الاستدعاء")
    payload: Any = Field(default=None, description="حمولة البروتوكول")
    grpc_metadata: Dict[str, str] = Field(default_factory=dict)


class TransportResponse(BaseModel):
    """عقد استجابة تطبيقية. `body` يحمل الكائن المفكك بعد L6 Deserialize."""
    model_config = ConfigDict(extra="allow")
    status_code: int = Field(default=200)
    body: Any = Field(default=None, description="الرد المفكك (كائن، dict، أو نص)")
    headers: Dict[str, str] = Field(default_factory=dict)


class TransportChunk(BaseModel):
    """عقد شريحة تدفق. `data` تحمل الحمولة الجزئية قبل/بعد ترميز L6."""
    model_config = ConfigDict(extra="allow")
    data: Any = Field(..., description="بيانات الشريحة (يتم معالجتها عبر L6 SSEStreamCodec)")
    done: bool = Field(default=False, description="إشارة انتهاء الدفق")


# ⚠️ تم إزالة TransportError من هذا الملف.
# استخدم الاستثناءات المعتمدة لكل طبقة مباشرةً:
# • transport.base.TransportError → لأخطاء النقل وإعادة المحاولة (L4/L5)
# • presentation.protocol.PresentationError → لأخطاء التسلسل والضغط (L6)
# • ValueError/TypeError → لأخطاء التحقق من المخططات التطبيقية (L7)

"""


🔍 التغييرات المعمارية ولماذا؟
التغيير
السبب المعماري
الأثر على النظام
إزالة timeout, max_retries, retry_delay
هذه إعدادات نقل/جلسة (L4/L5) وليست بيانات تطبيقية. وجودها هنا يكسر SRP ويسبب ازدواجية مع TransportConfig و RetryPolicyConfig.
✅ تنظيف واضح للحدود. التكوين يذهب لـ L4، والبيانات تبقى لـ L6/L7.
تحويل body: str → body: Any و data: str → data: Any
L6 يعمل مع bytes على السلك، لكنه يُعيد كائنات (dict, BaseModel) بعد deserialize. str كان يقيد المرونة ويسبب تحويلات يدوية غير ضرورية.
✅ JsonSerializer و SSEStreamCodec يعملان مباشرة دون طبقات تحويل إضافية.
exclude=True لـ target في InProcessRequest
Callable غير قابل للتسلسل JSON. إخفاؤه يمنع أخطاء JsonSerializer عند تمرير الطلب عبر شبكة.
✅ حماية وقت التشغيل من أخطاء التسلسل الصامتة.
إزالة TransportError
كان يخلق تعارضًا مع transport.base.TransportError (L4) و presentation.protocol.PresentationError (L6).
✅ توحيد معالجة الأخطاء حسب الطبقة، وتقليل الالتباس.
استخدام ConfigDict و Field
توحيد مع Pydantic v2 عبر المشروع، وتمكين model_dump()/model_validate() الأمثل.
✅ توافق كامل مع JsonSerializer الحالي وأدوات التحقق الثابت.








"""