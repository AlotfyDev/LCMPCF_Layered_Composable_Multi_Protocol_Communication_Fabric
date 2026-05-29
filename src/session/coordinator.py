# session/coordinator.py
"""
OSI Layer 5 Session Coordinator.
مسؤولية هذا المكون حصريًا:
- ترجمة أحداث النقل (L4 DeliveryReport / TransportError) إلى إجراءات سيشن (L5)
- تنسيق دورة حياة الحوار (refresh/close) بناءً على نجاح/فشل التسليم
- تنفيذ قرارات سياسة إعادة المحاولة (RetryHook) واستعادة نقاط التفتيش
- توفير واجهة موحدة وآمنة لـ L7 (BaseActor) للتعامل مع السياق دون اقتران بالنقل
لا يخزن حالة جلسة داخليًا، لا يعتمد على ناقل محدد، ويفوض كل العمليات للواجهات المجردة.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from transport.base import DeliveryReport, TransportError
from transport.context import TransportContext, RetryHook, RetryDecision
from session.protocol import ISessionLifecycle, ICheckpointSync

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CoordinationOutcome:
    """
    نتيجة تنسيقية موحدة تُعاد لـ L7 (BaseActor) بعد معالجة حدث L4.
    تحدد الإجراء التالي المتوقع دون كسر عزل الطبقات.
    """
    action: str  # "continue", "retry", "restored", "aborted"
    context: TransportContext
    checkpoint_id: Optional[str] = None
    reason: Optional[str] = None


class SessionCoordinator:
    """
    منسق أحداث الجلسة (OSI L5 Session Orchestrator).
    يربط تقارير التسليم الدقيقة من L4 بسلوكيات إدارة الجلسة ونقاط التفتيش من L5.
    """

    def __init__(
        self,
        lifecycle: ISessionLifecycle,
        checkpoint: ICheckpointSync,
        retry_hook: RetryHook,
        max_attempts: int = 3
    ):
        self.lifecycle = lifecycle
        self.checkpoint = checkpoint
        self.retry_hook = retry_hook
        self.max_attempts = max_attempts

    async def handle_success(self, report: DeliveryReport) -> CoordinationOutcome:
        """
        يُعالج تقرير تسليم ناجح من L4.
        يجدد عداد الخمول، ويسجل حدث التنسيق.
        """
        await self.lifecycle.refresh(report.context.session_id)
        logger.debug(
            f"L5 Coordination: refreshed session {report.context.session_id} "
            f"(offset={report.final_offset}, retries={report.retry_count})"
        )
        return CoordinationOutcome(action="continue", context=report.context)

    async def handle_failure(
        self, context: TransportContext, error: TransportError, attempt: int
    ) -> CoordinationOutcome:
        """
        يُعالج فشل تسليم من L4 عبر استشارة RetryHook وتنفيذ القرار.
        يعيد سياقًا محدثًا أو يُنهي الجلسة حسب السياسة.
        """
        decision = self.retry_hook(context, error, attempt, self.max_attempts)
        logger.info(f"L5 Coordination: decision='{decision}' for session={context.session_id}")

        if decision == "retry":
            return CoordinationOutcome(action="retry", context=context)

        if decision == "restore_checkpoint":
            return await self._execute_restore(context)

        # افتراضي: abort
        await self.lifecycle.close(context.session_id, reason=f"coordinator_abort:{error.error_type.value}")
        return CoordinationOutcome(
            action="aborted",
            context=context,
            reason=str(error)
        )

    async def _execute_restore(self, context: TransportContext) -> CoordinationOutcome:
        """يستعيد آخر نقطة تفتيش صالحة ويعيد بناء السياق مع الإزاحة الجديدة."""
        try:
            ckpt_id, payload = await self.checkpoint.get_latest(context.session_id)
            # استخلاص الإزاحة المحفوظة من الحمولة (افتراضيًا تعتمد على تنسيق L5 الداخلي)
            new_offset = self._extract_offset_from_payload(payload)
            
            # إنشاء سياق جديد محدث (TransportContext frozen)
            restored_ctx = context.model_copy(update={"stream_offset": new_offset})
            logger.info(f"L5 Restored session {context.session_id} from checkpoint {ckpt_id} (offset={new_offset})")
            return CoordinationOutcome(action="restored", context=restored_ctx, checkpoint_id=ckpt_id)
        except FileNotFoundError:
            logger.warning(f"No checkpoint found for {context.session_id}, aborting.")
            await self.lifecycle.close(context.session_id, reason="restore_failed_no_checkpoint")
            return CoordinationOutcome(action="aborted", context=context, reason="No valid checkpoint available")

    # ── واجهات صريحة لنقاط التفتيش (يُستدعى مباشرة من L7 عند الحاجة) ──

    async def mark_checkpoint(self, context: TransportContext, payload: bytes) -> str:
        """
        يدرج نقطة تفتيش جديدة في الدفق.
        يُستدعى عادةً بعد إكمال وحدة منطقية (Task/Message) أو تجاوز عتبة حجمية.
        """
        ckpt_id = await self.checkpoint.mark(context.session_id, payload)
        logger.debug(f"L5 Checkpoint marked: {ckpt_id} for session {context.session_id}")
        return ckpt_id

    async def restore_checkpoint(self, session_id: str, checkpoint_id: str) -> bytes:
        """استعادة صريحة لحمولة نقطة تفتيش محددة."""
        _, payload = await self.checkpoint.restore(session_id, checkpoint_id)
        return payload

    def _extract_offset_from_payload(self, payload: bytes) -> int:
        """
        دالة مساعدة لاستخراج stream_offset من حمولة نقطة التفتيش.
        يعتمد التنسيق على تطبيق L5 المحدد (CLI/InProcess/A2A).
        الافتراضي هنا يعتمد على بنية JSON بسيطة أو بايتات أولية.
        يمكن للمحولات تجاوز هذا السلوك عبر Composition.
        """
        try:
            import json
            data = json.loads(payload.decode("utf-8", errors="ignore"))
            return data.get("stream_offset", 0)
        except Exception:
            # Fallback: قراءة أول 8 بايت كـ int (Little Endian)
            if len(payload) >= 8:
                import struct
                return struct.unpack("<Q", payload[:8])[0]
            return 0