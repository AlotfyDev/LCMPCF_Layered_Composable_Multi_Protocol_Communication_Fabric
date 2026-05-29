# transport/channel/types.py
"""
أنواع وقواعد بيانات القناة (Channel State, Errors, Metrics).
معزولة تمامًا عن المنطق التشغيلي لضمان إعادة الاستخدام وسهولة الاختبار.
"""
from __future__ import annotations

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional


class ChannelState(Enum):
    """حالات دورة حياة القناة المعتمدة معماريًا."""
    CLOSED = "closed"
    CONNECTING = "connecting"
    ACTIVE = "active"
    DRAINING = "draining"
    FAILED = "failed"


class ChannelError(Exception):
    """استثناء خاص بانتهاكات حالة القناة أو فشل دورة الحياة."""
    def __init__(self, message: str, state: Optional[ChannelState] = None):
        super().__init__(message)
        self.state = state


@dataclass
class ChannelMetrics:
    """
    مقاييس أداء القناة (قابل للتوسيع لـ Observability/Telemetry).
    مُجمّد جزئيًا لمنع التعديل العرضي، يُحدّث عبر الـ Channel فقط.
    """
    opened_at: Optional[float] = None
    closed_at: Optional[float] = None
    messages_sent: int = 0
    bytes_sent: int = 0
    errors: int = 0