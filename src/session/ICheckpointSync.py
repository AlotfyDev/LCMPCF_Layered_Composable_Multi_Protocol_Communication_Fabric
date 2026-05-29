from abc import ABC, abstractmethod
from typing import Optional, Sequence
from pydantic import BaseModel

class CheckpointMeta(BaseModel):
    checkpoint_id: str
    created_at: float
    stream_offset: int  # مؤشر موقع في تدفق البيانات
    size_bytes: int

class PrunePolicy(BaseModel):
    max_checkpoints: int = 10
    max_age_seconds: float = 7200.0
    keep_last: int = 3

class ICheckpointSync(ABC):
    @abstractmethod
    async def mark(self, session_id: str, payload: bytes, meta: Optional[CheckpointMeta] = None) -> str:
        """
        يدرج نقطة تفتيش (Checkpoint) في تدفق الجلسة.
        payload: حالة جزئية أو مؤشر موقع في الدفق (يعامل كـ opaque bytes).
        يعيد checkpoint_id فريدًا.
        """
        ...

    @abstractmethod
    async def get_latest(self, session_id: str) -> tuple[str, bytes]:
        """
        يجلب آخر نقطة تفتيش صالحة للجلسة.
        يعيد (checkpoint_id, payload).
        يرفع SessionCheckpointNotFoundError إذا لم توجد نقاط.
        """
        ...

    @abstractmethod
    async def restore(self, session_id: str, checkpoint_id: str) -> bytes:
        """
        يستعيد حالة الجلسة من نقطة تفتيش محددة.
        يستخدم بعد انقطاع/عطل لاستئناف النقل من الموقع المحفوظ.
        """
        ...

    @abstractmethod
    async def prune(self, session_id: str, policy: PrunePolicy) -> int:
        """
        ينظف نقاط التفتيش القديمة أو الزائدة لتجنب إهدار الموارد.
        يعيد عدد العناصر المحذوفة.
        """
        ...

    @abstractmethod
    async def list(self, session_id: str) -> Sequence[CheckpointMeta]:
        """
        يسرد نقاط التفتيش المتاحة للجلسة مع بياناتها الوصفية.
        """
        ...