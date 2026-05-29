# transport/base.py
"""
OSI Layer 4 Transport Contract.
مسؤولية هذه الطبقة حصريًا: تسليم الشرائح (Segments)، التحكم في التدفق (Flow Control)، 
تصنيف الأخطاء (Error Classification)، وإعداد تقارير التسليم (Delivery Reports).
لا تخزن حالة جلسة، لا تفسر سياقًا، ولا تعتمد على L5/L7.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import AsyncIterator, Callable, Awaitable

from .context import TransportContext, RetryHook, RetryDecision


class Direction(Enum):
    """اتجاه القناة بالنسبة للناقل الحالي."""
    OUTBOUND = "outbound"  # نرسل بيانات لطرف خارجي
    INBOUND = "inbound"    # نستقبل بيانات من طرف خارجي


class ErrorType(Enum):
    """تصنيف أخطاء النقل حسب قابلية الاستعادة (L4 Error Control)."""
    TRANSIENT = "transient"      # عطل مؤقت (timeout, network reset) → قابل للإعادة
    PERMANENT = "permanent"      # عطل نهائي (auth fail, closed, invalid) → لا إعادة محاولة
    POLICY = "policy"            # قرار سياسة (rate limit, hook abort) → توجيه لـ L5


@dataclass(frozen=True)
class TransportError(Exception):
    """استثناء نقل موحد مع تصنيف صريح لسياسات L4/L5."""
    error_type: ErrorType
    message: str
    status_code: int | None = None
    retry_after: float | None = None


@dataclass(frozen=True)
class DeliveryReport:
    """تقرير تسليم شريحة (Segment Delivery Report).
    يعيد لـ L5 حالة النقل الدقيقة لتمكين المزامنة ونقاط التفتيش.
    """
    success: bool
    context: TransportContext
    bytes_sent: int
    bytes_received: int
    final_offset: int
    error: TransportError | None = None
    retry_count: int = 0


class BaseTransporter(ABC):
    """
    العقد الأساسي لنقل البيانات (OSI L4).
    ينفذ التسليم من طرف لطرف، ويصنف الأخطاء، ويعيد تقارير تسليم دقيقة.
    كل محول ملموس (Subprocess, InProcess, TCP, UDS) يرث هذا الكلاس.
    """

    def __init__(self, direction: Direction = Direction.OUTBOUND):
        self._direction = direction

    @property
    def direction(self) -> Direction:
        return self._direction

    # ── Outbound: تسليم الشرائح مع سياق الجلسة ──────────────

    @abstractmethod
    async def send(self, payload: bytes, context: TransportContext) -> DeliveryReport:
        """
        تسليم حمولة بايتات مع سياق جلسة شفاف.
        يتعامل مع: التجزئة، إعادة الإرسال، التحكم في التدفق، وإرجاع تقرير دقيق.
        """
        ...

    @abstractmethod
    async def stream(
        self, payload: bytes, context: TransportContext
    ) -> AsyncIterator[bytes]:
        """
        بث حمولة على شكل شرائح متدفقة مع دعم الضغط العكسي (Backpressure).
        السياق يُستخدم لتتبع `stream_offset` ومزامنة الدفق.
        """
        ...

    # ── Inbound: استقبال الشرائح ────────────────────────────

    @abstractmethod
    async def serve(
        self, handler: Callable[[bytes, TransportContext], Awaitable[bytes]]
    ) -> None:
        """
        الاستماع للوصلات الواردة، استخراج السياق (من الهيدر/البيئة/الإطار)،
        واستدعاء المعالج مع الحمولة والسياق المستخرج.
        """
        ...

    # ── Lifecycle ──────────────────────────────────────────

    @abstractmethod
    async def close(self) -> None:
        """تحرير موارد القناة (مآخذ، عمليات فرعية، طوابب)."""
        ...

    async def __aenter__(self) -> BaseTransporter:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    # ── L4 Error Classification & Policy Hook Support ──────

    def classify_error(self, exception: Exception) -> TransportError:
        """
        تصنيف الاستثناءات الخام إلى أنواع L4 معيارية.
        تُستخدم من قبل RetryPolicy لاتخاذ قرار الإعادة أو الإنهاء.
        يمكن للمحولات الملموسة تجاوز هذا السلوك إذا لزم.
        """
        msg = str(exception).lower()
        if any(kw in msg for kw in ("timeout", "reset", "broken pipe", "temporarily")):
            return TransportError(ErrorType.TRANSIENT, str(exception))
        if any(kw in msg for kw in ("refused", "forbidden", "unauthorized", "closed")):
            return TransportError(ErrorType.PERMANENT, str(exception))
        # افتراضي: عطل غير مصنف → تعامل كعابر آمنًا
        return TransportError(ErrorType.TRANSIENT, str(exception))

    def build_retry_decision_hook(self) -> RetryHook:
        """
        نقطة تمكين لـ L5 لحقن سياسة إعادة المحاولة.
        يُستدعى داخليًا من RetryPolicy قبل كل محاولة إعادة إرسال.
        المحولات لا تنفذه مباشرة، بل تمرره لـ L4 retry engine.
        """
        ...