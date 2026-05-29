# transport/retry.py
"""
OSI Layer 4 Retry & Flow Control Engine.
مسؤولية هذا المحرك حصريًا:
- تصنيف أخطاء النقل (Transient vs Permanent)
- تنفيذ التأخير الأسي (Exponential Backoff) ضمن حدود السياسة
- استدعاء خطاف L5 التعاوني (RetryHook) قبل كل إعادة محاولة
- إعداد تقارير تسليم دقيقة (DeliveryReport) تعكس حالة الاستعادة
لا يخزن حالة جلسة، لا يفسر سياقًا، ويعزل الآلية عن السياسة.
"""
from __future__ import annotations

import asyncio
import dataclasses
import logging
from typing import AsyncIterator, Awaitable, Callable, Optional

from transport.context import RetryDecision, RetryHook, TransportContext
from transport.base import DeliveryReport, ErrorType, TransportError
from transport.config import RetryPolicyConfig

logger = logging.getLogger(__name__)


class RetryEngine:
    """
    محرك إعادة المحاولة وتحكم التدفق (L4 Mechanism).
    يُغلّف عمليات النقل (send/stream) بآلية استعادة ذكية،
    ويفوض قرارات السياسة لـ L5 عبر RetryHook.
    """

    def __init__(
        self,
        config: RetryPolicyConfig,
        hook: Optional[RetryHook] = None,
        error_classifier: Optional[Callable[[Exception], TransportError]] = None
    ):
        self.config = config
        self.hook = hook
        self.classify = error_classifier or self._default_classifier

    @staticmethod
    def _default_classifier(exc: Exception) -> TransportError:
        """تصنيف افتراضي للأخطاء حسب قابلية الاستعادة (Cloudflare L4 Error Control)."""
        msg = str(exc).lower()
        if any(k in msg for k in ("timeout", "reset", "broken pipe", "temporarily", "unavailable")):
            return TransportError(ErrorType.TRANSIENT, str(exc))
        return TransportError(ErrorType.PERMANENT, str(exc))

    def _consult_hook(self, ctx: TransportContext, err: TransportError, attempt: int) -> RetryDecision:
        """استشارة سياسة L5 قبل اتخاذ قرار إعادة المحاولة."""
        if self.hook:
            try:
                return self.hook(ctx, err, attempt, self.config.max_attempts)
            except Exception as e:
                logger.error(f"Retry hook execution failed: {e}. Defaulting to abort.")
                return "abort"
        # سلوك L4 الافتراضي عند عدم وجود خطاف
        return "retry" if err.error_type == ErrorType.TRANSIENT else "abort"

    async def execute_with_retry(
        self,
        operation: Callable[[], Awaitable[DeliveryReport]],
        context: TransportContext
    ) -> DeliveryReport:
        """
        ينفذ عملية إرسال واحدة مع إعادة محاولة ذكية.
        يعيد DeliveryReport محدثًا بعدد المحاولات والحالة النهائية.
        """
        last_error: Optional[Exception] = None
        
        for attempt in range(1, self.config.max_attempts + 1):
            try:
                report = await operation()
                if report.success:
                    # تحديث عدد المحاولات في التقرير الناجح (Frozen dataclass)
                    return dataclasses.replace(report, retry_count=attempt - 1)

                # فشل مُبلغ عنه من الناقل دون استثناء
                last_error = report.error or RuntimeError("Operation reported failure")
                raise last_error

            except Exception as exc:
                last_error = exc
                transport_err = self.classify(exc) if not isinstance(exc, TransportError) else exc
                decision = self._consult_hook(context, transport_err, attempt)

                if decision in ("abort", "restore_checkpoint"):
                    logger.warning(f"Retry interrupted by hook decision='{decision}' at attempt {attempt}")
                    return DeliveryReport(
                        success=False, context=context, bytes_sent=0, bytes_received=0,
                        final_offset=context.stream_offset, error=transport_err, retry_count=attempt - 1
                    )

                if decision == "retry" and attempt < self.config.max_attempts:
                    delay = self.config.initial_timeout * (self.config.backoff_factor ** (attempt - 1))
                    delay = min(delay, self.config.max_timeout)
                    logger.debug(f"Backing off for {delay:.2f}s (attempt {attempt})")
                    await asyncio.sleep(delay)
                    continue

                # خطأ دائم أو تجاوز الحد الأقصى
                break

        # حالة الفشل النهائية
        final_err = last_error if isinstance(last_error, TransportError) else self.classify(last_error)
        return DeliveryReport(
            success=False, context=context, bytes_sent=0, bytes_received=0,
            final_offset=context.stream_offset, error=final_err, retry_count=self.config.max_attempts
        )

    async def stream_with_retry(
        self,
        stream_operation: Callable[[], Awaitable[AsyncIterator[bytes]]],
        context: TransportContext
    ) -> AsyncIterator[bytes]:
        """
        يبث دفقة بايتات مع إعادة محاولة عند فشل التهيئة أو الانقطاع.
        ملاحظة: إعادة المحاولة في منتصف الدفق تتطلب دعم L4 Transporter
        لإعادة ضبط المؤشر (stream_offset) قبل كل محاولة.
        """
        for attempt in range(1, self.config.max_attempts + 1):
            try:
                iterator = await stream_operation()
                async for chunk in iterator:
                    yield chunk
                return  # اكتمل البث بنجاح

            except Exception as exc:
                transport_err = self.classify(exc) if not isinstance(exc, TransportError) else exc
                decision = self._consult_hook(context, transport_err, attempt)

                if decision != "retry" or attempt == self.config.max_attempts:
                    logger.error(f"Stream terminated permanently after {attempt} attempts: {transport_err.message}")
                    raise transport_err

                delay = self.config.initial_timeout * (self.config.backoff_factor ** (attempt - 1))
                delay = min(delay, self.config.max_timeout)
                logger.warning(f"Stream interrupted, retrying after {delay:.2f}s (attempt {attempt})")
                await asyncio.sleep(delay)
                # ملاحظة: يجب على الناقل الملموس إعادة ضبط الحالة الداخلية قبل الاستئناف