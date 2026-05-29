# session/hooks/retry_hooks.py
"""
OSI Layer 5 Retry Policy Templates (RetryHook Implementations).
مسؤولية هذه القوالب حصريًا:
- اتخاذ قرارات سياسة إعادة المحاولة بناءً على تصنيف الخطأ (L4) وعدد المحاولات
- تحديد متى يُعاد الإرسال، متى تُستعاد نقطة التفتيش، ومتى تُنهي الجلسة بأمان
- البقاء محايدة تمامًا للنقل، لا تخزن حالة، ولا تنفذ إجراءات استعادة (تفوضها لـ SessionCoordinator)
تتوافق 100% مع بروتوكول transport.context.RetryHook.
"""
from __future__ import annotations

import logging
from typing import Optional
from transport.context import RetryHook, RetryDecision, TransportContext
from transport.base import TransportError, ErrorType

logger = logging.getLogger(__name__)


class CheckpointRestoreHook(RetryHook):
    """
    سياسة استعادة نقاط التفتيش عند الفشل.
    - على أخطاء عابرة (TRANSIENT): تعيد المحاولة حتى استنفاد الحد الأقصى
    - على أخطاء دائمة (PERMANENT) أو تجاوز المحاولات: تقرر استعادة آخر نقطة تفتيش
    - مناسبة لسيناريوهات: معالجة ملفات ضخمة، جلسات حوار طويلة، عمليات CLI متقطعة
    """
    def __init__(self, max_restore_attempts: int = 1):
        if max_restore_attempts < 0:
            raise ValueError("max_restore_attempts must be >= 0")
        self.max_restore_attempts = max_restore_attempts

    def __call__(
        self,
        context: TransportContext,
        error: Exception,
        attempt: int,
        max_attempts: int
    ) -> RetryDecision:
        # تصنيف الخطأ إذا كان TransportError مصنفًا من L4
        is_permanent = False
        if isinstance(error, TransportError):
            is_permanent = error.error_type == ErrorType.PERMANENT

        if is_permanent or attempt >= max_attempts:
            if self.max_restore_attempts > 0:
                logger.info(
                    f"Retry policy: permanent/exhausted → restore_checkpoint "
                    f"(session={context.session_id}, attempt={attempt})"
                )
                return "restore_checkpoint"
            return "abort"

        # خطأ عابر ضمن الحدود → إعادة محاولة
        return "retry"


class GracefulAbortHook(RetryHook):
    """
    سياسة الإنهاء الآمن والسريع عند الفشل.
    - على أخطاء دائمة: تنهي الجلسة فورًا دون إعادة محاولة
    - على أخطاء عابرة: تسمح بإعادة محاولة واحدة فقط (اختياري)، ثم تنهي
    - مناسبة لسيناريوهات: معالجة معاملات حساسة، عمليات غير قابلة للاستئناف، بيئات محدودة الموارد
    """
    def __init__(self, allow_single_retry: bool = False, strict_on_permanent: bool = True):
        self.allow_single_retry = allow_single_retry
        self.strict_on_permanent = strict_on_permanent

    def __call__(
        self,
        context: TransportContext,
        error: Exception,
        attempt: int,
        max_attempts: int
    ) -> RetryDecision:
        is_permanent = False
        if isinstance(error, TransportError):
            is_permanent = error.error_type == ErrorType.PERMANENT

        if is_permanent and self.strict_on_permanent:
            logger.warning(
                f"Retry policy: permanent error → immediate abort "
                f"(session={context.session_id})"
            )
            return "abort"

        if not self.allow_single_retry or attempt >= 1:
            logger.info(
                f"Retry policy: exhausted/strict → abort "
                f"(session={context.session_id}, attempt={attempt})"
            )
            return "abort"

        return "retry"


# ── Hook Factory (لربط YAML hook_type بالتنفيذ الفعلي) ──────────────

HOOK_REGISTRY = {
    "checkpoint_restore": CheckpointRestoreHook,
    "graceful_abort": GracefulAbortHook,
    # يمكن إضافة سياسات مخصصة هنا لاحقًا
}

def create_retry_hook(hook_type: str, **kwargs) -> RetryHook:
    """
    ينشئ مثيل RetryHook بناءً على معرف تصريحي من TransportConfig.
    يرفع ValueError إذا كان النوع غير مسجل.
    """
    hook_cls = HOOK_REGISTRY.get(hook_type)
    if not hook_cls:
        raise ValueError(
            f"Unknown retry hook type: '{hook_type}'. "
            f"Available: {list(HOOK_REGISTRY.keys())}"
        )
    return hook_cls(**kwargs)