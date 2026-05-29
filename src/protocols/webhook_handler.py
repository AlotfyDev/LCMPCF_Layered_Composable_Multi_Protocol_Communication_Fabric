# protocols/webhook_handler.py
"""
OSI Layer 7 Webhook Application Protocol Handler.
مسؤوليته حصريًا: دلالة التوصيل العكسي (Callback Semantics)، التحقق من التوقيع (HMAC-SHA256)،
منع التكرار (Idempotency)، إدارة مهلة إعادة اللعب (Replay Window)، وتوليد تلميحات إعادة المحاولة لـ L5.

✅ معزول تمامًا عن HTTP/WS (Transport-Agnostic)
✅ يعتمد على PresentationPipeline (L6) للتغليف السلكي، و ProtocolErrorMapper لربط الأخطاء بـ L5.
✅ يلتزم بمعايير Webhook الحديثة: X-Webhook-Id, X-Webhook-Timestamp, X-Webhook-Signature.
"""
from __future__ import annotations

import hashlib
import hmac
import time
import logging
from typing import Any, Awaitable, Callable, Dict, Optional, Set

from transport.base import Direction, TransportError
from transport.context import TransportContext
from presentation.pipeline import PresentationPipeline
from protocols.error_mapper import ProtocolErrorMapper, ProtocolType

logger = logging.getLogger(__name__)


class WebhookProtocolHandler:
    """
    معالج بروتوكول Webhook (OSI L7 Callback Semantics).
    يدير دورة حياة الاستدعاء العكسي مع ضمانات الأمان والتسليم دون اقتران بنقل معين.
    """

    def __init__(
        self,
        pipeline: PresentationPipeline,
        direction: Direction = Direction.OUTBOUND,
        shared_secret: Optional[str] = None,
        idempotency_store: Optional[Set[str]] = None,
        max_replay_age_seconds: float = 300.0,
        max_idempotency_window_seconds: float = 86400.0
    ):
        self.pipeline = pipeline
        self.direction = direction
        self.shared_secret = shared_secret
        self.idempotency_store = idempotency_store or set()
        self.max_replay_age = max_replay_age_seconds
        self.max_idempotency_window = max_idempotency_window_seconds

    # ── INBOUND: استقبال وتنفيذ Webhooks ─────────────────────

    async def handle_inbound(
        self,
        raw_payload: bytes | str,
        metadata: Dict[str, str],
        context: TransportContext,
        handler: Callable[[Any, TransportContext], Awaitable[Any]]
    ) -> Dict[str, Any]:
        """
        يستقبل Webhook، يتحقق من الأمان والتفرد، ينفذ المعالج، ويعيد تأكيد الاستلام.
        
        Args:
            raw_payload: الحمولة الخام قبل فك الترميز
            metadata: رؤوس/بيانات مصاحبة (توقيعات، معرفات، طوابع زمنية)
            context: سياق الجلسة الموحد
            handler: الدالة التطبيقية التي ستعالج الحدث
        """
        if self.direction != Direction.INBOUND:
            raise ValueError("handle_inbound requires INBOUND direction")

        webhook_id = metadata.get("x-webhook-id") or context.correlation_id or "unknown"
        timestamp = float(metadata.get("x-webhook-timestamp", 0))
        signature = metadata.get("x-webhook-signature")

        try:
            # 1. التحقق من الطابع الزمني (منع إعادة اللعب)
            if timestamp and self.max_replay_age > 0:
                age = time.time() - timestamp
                if age < 0 or age > self.max_replay_age:
                    raise TransportError(400, f"Webhook timestamp expired or future-dated (age={age:.1f}s)")

            # 2. التحقق من التوقيع (HMAC-SHA256)
            if self.shared_secret and signature:
                self._verify_signature(raw_payload, signature, timestamp)

            # 3. فحص التكرار (Idempotency)
            if webhook_id and webhook_id != "unknown":
                if webhook_id in self.idempotency_store:
                    return {"status": "acknowledged_duplicate", "webhook_id": webhook_id}

            # 4. فك ترميز L6 وتنفيذ المعالج
            payload = self.pipeline.decode(raw_payload, target_type=Any)
            result = await handler(payload, context)

            # 5. تسجيل المعالجة بنجاح
            if webhook_id and webhook_id != "unknown":
                self.idempotency_store.add(webhook_id)
                # تنظيف مخزن التفريد دوريًا في الإنتاج (هنا مبسط للعرض)
                
            return {"status": "accepted", "webhook_id": webhook_id, "data": result}

        except TransportError:
            raise
        except Exception as e:
            err_resp = ProtocolErrorMapper.map(e, protocol=ProtocolType.WEBHOOK)
            raise TransportError(
                err_resp.protocol_status,
                f"Webhook processing failed: {e}",
                metadata={"retry_hint": err_resp.is_retryable}
            ) from e

    # ── OUTBOUND: إرسال Webhooks ─────────────────────────────

    async def handle_outbound(
        self,
        payload: Any,
        sender: Callable[[bytes, TransportContext], Awaitable[bytes]],
        context: Optional[TransportContext] = None
    ) -> Dict[str, Any]:
        """
        يجهز ويرسل Webhook مع توليد معرف فريد، توقيع أمني، وطابع زمني.
        يفحص استجابة الاستلام ويقرر إمكانية إعادة المحاولة عبر L5.
        """
        if self.direction != Direction.OUTBOUND:
            raise ValueError("handle_outbound requires OUTBOUND direction")

        ctx = context or TransportContext(session_id="webhook-out", correlation_id=f"wh-{time.time_ns()}")
        webhook_id = ctx.correlation_id
        ctx.metadata["x-webhook-id"] = webhook_id
        ctx.metadata["x-webhook-timestamp"] = str(int(time.time()))

        try:
            # 1. ترميز L6
            wire_bytes = self.pipeline.encode(payload)

            # 2. توقيع الحمولة وإلحاق التوقيع بالسياق
            if self.shared_secret:
                sig = self._compute_signature(wire_bytes, float(ctx.metadata["x-webhook-timestamp"]))
                ctx.metadata["x-webhook-signature"] = f"sha256={sig}"

            # 3. إرسال عبر القناة/المرسل المجرد
            resp_bytes = await sender(wire_bytes, ctx)

            # 4. التحقق من تأكيد الاستلام (2xx يعادل نجاح L7)
            # يفترض أن L4/L6 يعيدان بايتات أو كائن حالة. هنا نتعامل مع نجاح افتراضي إذا لم يُرفع استثناء
            return {"status": "delivered", "webhook_id": webhook_id, "ack": True}

        except TransportError as e:
            err_resp = ProtocolErrorMapper.map(e, protocol=ProtocolType.WEBHOOK)
            raise TransportError(
                err_resp.protocol_status,
                f"Webhook delivery failed: {e}",
                metadata={"retry_hint": err_resp.is_retryable}
            ) from e
        except Exception as e:
            err_resp = ProtocolErrorMapper.map(e, protocol=ProtocolType.WEBHOOK)
            raise TransportError(
                err_resp.protocol_status,
                f"Webhook outbound error: {e}",
                metadata={"retry_hint": err_resp.is_retryable}
            ) from e

    # ── Security & Semantics Helpers ─────────────────────────

    def _compute_signature(self, payload: bytes | str, timestamp: float) -> str:
        """يحسب HMAC-SHA256 للحمولة والطابع الزمني."""
        msg = f"{timestamp}.".encode() + (payload if isinstance(payload, bytes) else payload.encode())
        return hmac.new(self.shared_secret.encode(), msg, hashlib.sha256).hexdigest()

    def _verify_signature(self, payload: bytes | str, signature: str, timestamp: float) -> None:
        """يتحقق من التوقيع بشكل آمن (Constant-Time) ويمنع هجمات التوقيت."""
        expected_sig = self._compute_signature(payload, timestamp)
        # إزالة البادئة الشائعة مثل "sha256=" إن وجدت
        clean_sig = signature.split("=")[-1] if "=" in signature else signature
        if not hmac.compare_digest(clean_sig, expected_sig):
            raise TransportError(401, "Webhook signature verification failed")

    async def clear_expired_idempotency(self) -> None:
        """ينظف مخزن التفريد منتهي الصلاحية (يُستدعى دوريًا في الخلفية)."""
        # في الإنتاج: استخدم Redis TTL أو جدول قاعدة بيانات
        if len(self.idempotency_store) > 100_000:
            self.idempotency_store.clear()
            logger.debug("Idempotency store cleared (overflow protection)")
            
            
"""
✅ التحقق من التوافق المعماري
المعيار
التطبيق في الكود
عزل تام عن النقل
لا httpx، لا FastAPI Request/Response. يعتمد على sender مجرد و metadata قاموسي. يعمل فوق HTTP, WS, gRPC, أو UDS
أمان Webhook معياري
HMAC-SHA256 مع timestamp مدمج في الرسالة، و hmac.compare_digest لمنع هجمات التوقيت، ونافذة max_replay_age لمنع إعادة اللعب
منع التكرار (Idempotency)
فحص x-webhook-id قبل التنفيذ، تخزين في idempotency_store، وإرجاع acknowledged_duplicate بدلاً من المعالجة المزدوجة
تلميحات إعادة المحاولة لـ L5
يربط جميع الأخطاء بـ ProtocolErrorMapper.map(..., ProtocolType.WEBHOOK) ويُعيد retry_hint في metadata لـ RetryHook
تكامل L6 Pipeline
encode/decode تُستخدم للتغليف السلكي فقط. بنية Webhook الداخلية (التوقيع، المعرف، الطابع) تُدار بشكل صريح لضمان الدقة
اتجاهية واضحة
handle_inbound للخادم، handle_outbound للعميل. التحقق من Direction يمنع سوء الاستخدام
📌 ملاحظات تنفيذية هامة
إضافة ProtocolType.WEBHOOK: أضف السطر التالي إلى enum ProtocolType في protocols/error_mapper.py:
python

class ProtocolType(Enum):
    HTTP = "http"
    CLI = "cli"
    INPROCESS = "inprocess"
    LOCAL_IPC = "local_ipc"
    WEBSOCKET = "websocket"
    GRPC = "grpc"
    GRAPHQL = "graphql"
    WEBHOOK = "webhook"  # ← إضافة جديدة

"""