# transport/context/retry_hook.py
"""
RetryHook: بروتوكول خطاف تعاوني يُستدعى من L4 عند فشل عابر في النقل.
يمكّن L5 من تطبيق سياسة الاستعادة (Policy) دون اقترانها بآلية إعادة المحاولة (Mechanism).
"""
from typing import Protocol, Literal, runtime_checkable
from .transport_context import TransportContext

# قرارات السياسة التي يمكن لـ L5 إرجاعها عند استدعاء الخطاف
RetryDecision = Literal[
    "retry",               # إعادة محاولة الإرسال بنفس السياق
    "abort",               # إنهاء الجلسة وإخطار الطبقة العليا
    "restore_checkpoint"   # استعادة حالة الجلسة من آخر نقطة تفتيش معروفة
]

@runtime_checkable
class RetryHook(Protocol):
    """
    بروتوكول خطاف إعادة المحاولة.
    ✅ Protocol Compliance:
       - يعتمد على Duck Typing مع `@runtime_checkable` للتحقق الآمن.
       - توقيع `__call__` صارم يضمن توافق جميع التنفيذات مع سياسة L4.
       - لا يرث من أي كلاس، مما يحافظ على عزله عن هرمية L4.
    🔄 دورة الاستدعاء:
       L4 يكتشف فشلًا عابرًا → يستدعي hook(ctx, error, attempt, max_attempts)
       L5 يقرر السياسة → L4 ينفذ القرار (إعادة، استعادة، أو إنهاء)
    """
    def __call__(
        self,
        context: TransportContext,
        error: Exception,
        attempt: int,
        max_attempts: int
    ) -> RetryDecision:
        """
        يقرر إجراء الاستعادة بناءً على سياق الجلسة ونوع الخطأ وعدد المحاولات.
        
        Args:
            context: سياق النقل الحالي (يحتوي session_id, stream_offset, إلخ)
            error: الاستثناء الذي تسبب في فشل النقل
            attempt: رقم المحاولة الحالية (1-based)
            max_attempts: الحد الأقصى للمحاولات المسموح بها
            
        Returns:
            قرار السياسة: "retry", "abort", أو "restore_checkpoint"
        """
        ...