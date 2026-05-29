# transport/config/transport_config.py
"""
نموذج تكوين النقل (L4 Transport Config).
✅ Pydantic v2 Strict: frozen=True, extra='forbid', validators صارمين.
✅ Factory-Ready: كل حقل مُصمم ليُقرأ مرة واحدة عند التهيئة، دون طفرات جانبية.
✅ L4/L5 Boundary Aware: يفصل بين آلية النقل (L4) وسياسة الجلسة (L5) عبر hook_type و context_defaults.
✅ WebSocket-Ready: يدعم تكوين القنوات ثنائية الاتجاه المتزامنة مع سياسات Keep-Alive.
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, ConfigDict, model_validator
from enum import StrEnum


class TransportType(StrEnum):
    """أنواع القنوات المدعومة في الطبقة الرابعة."""
    CLI = "cli"
    INPROCESS = "inprocess"
    TCP = "tcp"
    UDS = "uds"
    HTTP = "http"
    A2A = "a2a"
    WEBSOCKET = "websocket"  # ← إضافة WebSocket كناقل رسمي L4


class RetryPolicyConfig(BaseModel):
    """سياسة التحكم في التدفق واستعادة الأخطاء (L4 Error/Flow Control)."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_attempts: int = Field(default=3, ge=1, le=10, description="الحد الأقصى لمحاولات إعادة الإرسال")
    backoff_factor: float = Field(default=1.5, gt=0.0, description="معامل التأخير الأسي بين المحاولات")
    initial_timeout: float = Field(default=5.0, gt=0.0, description="مهلة الانتظار الأولية (ثواني)")
    max_timeout: float = Field(default=60.0, gt=0.0, description="الحد الأقصى للمهلة قبل الإنهاء")
    hook_type: Optional[str] = Field(
        default=None,
        description="معرف استراتيجية خطاف L5 (يُحل إلى RetryHook callable عبر Factory)"
    )
    hook_kwargs: Dict[str, Any] = Field(
        default_factory=dict,
        description="معاملات ديناميكية تُمرر لمنشئ RetryHook المحدد بـ hook_type",
        json_schema_extra={"examples": [
            {"max_restore_attempts": 1},  # لـ CheckpointRestoreHook
            {"allow_single_retry": True}   # لـ GracefulAbortHook (تم تصحيح true إلى True)
        ]}
    )


class ContextDefaultsConfig(BaseModel):
    """افتراضات سياق الجلسة التي سيستخدمها L5 لإدارة الحوار ونقاط التفتيش."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    default_ttl_seconds: float = Field(default=3600.0, gt=0.0)
    idle_timeout_seconds: float = Field(default=300.0, gt=0.0)
    offset_granularity: Literal["byte", "message", "chunk"] = Field(
        default="message",
        description="وحدة قياس stream_offset لنقاط التفتيش"
    )
    metadata_template: Dict[str, str] = Field(default_factory=dict)


class ChannelSettingsConfig(BaseModel):
    """إعدادات القناة المادية/المنطقية الخاصة بنوع النقل."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    subprocess_cmd: Optional[list[str]] = None
    env_overrides: Dict[str, str] = Field(default_factory=dict)
    socket_path: Optional[str] = None
    endpoint_url: Optional[str] = None
    port: Optional[int] = Field(default=None, ge=1, le=65535)
    headers: Dict[str, str] = Field(default_factory=dict)

    # ── WebSocket-Specific Fields (L4 Framing & Keep-Alive) ──
    ws_path: Optional[str] = Field(default="/", description="مسار ترقية WebSocket (Upgrade Path)")
    ping_interval: Optional[float] = Field(default=30.0, gt=0.0, description="فاصل إرسال Ping للكشف عن الانقطاع الصامت (ثواني)")
    pong_timeout: Optional[float] = Field(default=10.0, gt=0.0, description="مهلة انتظار Pong قبل اعتبار القناة معطلة (ثواني)")
    max_message_size: Optional[int] = Field(default=1048576, gt=0, description="الحد الأقصى لحجم رسالة WebSocket (بايت)")
    subprotocols: Optional[List[str]] = Field(default_factory=list, description="بروتوكولات فرعية متفاوض عليها (e.g., 'graphql-ws', 'a2a-v1')")


class TransportConfig(BaseModel):
    """
    التكوين الشامل للطبقة الرابعة (L4 Transport Configuration).
    يُستهلك حصريًا من قبل TransportFactory لربط:
    - نوع الناقل → المحول الملموس (subprocess, tcp, inprocess, websocket...)
    - سياسة الأخطاء → RetryPolicy + L5 RetryHook
    - سياق الجلسة → TransportContext defaults
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    transport_type: TransportType
    direction: Literal["outbound", "inbound"] = Field(default="outbound")
    retry_policy: RetryPolicyConfig = Field(default_factory=RetryPolicyConfig)
    context_defaults: ContextDefaultsConfig = Field(default_factory=ContextDefaultsConfig)
    channel: ChannelSettingsConfig = Field(default_factory=ChannelSettingsConfig)

    @model_validator(mode='after')
    def _validate_channel_requirements(self) -> TransportConfig:
        """فرض الحقول الإلزامية لكل نوع نقل لمنع تكوينات غير صالحة."""
        if self.transport_type == TransportType.CLI and not self.channel.subprocess_cmd:
            raise ValueError("نقل CLI يتطلب تحديد 'channel.subprocess_cmd'")
            
        # تم توسيع الشرط ليشمل WEBSOCKET
        network_types = (TransportType.TCP, TransportType.HTTP, TransportType.A2A, TransportType.WEBSOCKET)
        if self.transport_type in network_types:
            if not self.channel.endpoint_url and not self.channel.port:
                raise ValueError(f"نقل {self.transport_type.value} يتطلب 'channel.endpoint_url' أو 'channel.port'")
                
        if self.transport_type == TransportType.UDS and not self.channel.socket_path:
            raise ValueError("نقل UDS يتطلب تحديد 'channel.socket_path'")
            
        return self