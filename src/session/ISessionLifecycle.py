from abc import ABC, abstractmethod
from typing import Optional
from pydantic import BaseModel
from enum import Enum

class SessionStatus(Enum):
    ACTIVE = "active"
    IDLE = "idle"
    EXPIRED = "expired"
    CLOSED = "closed"

class SessionConfig(BaseModel):
    ttl_seconds: float = 3600.0          # أقصى عمر للجلسة
    idle_timeout_seconds: float = 300.0  # إغلاق تلقائي عند الخمول
    metadata: dict[str, str] = {}        # وسوم تعريفية (محايدة)

class ISessionLifecycle(ABC):
    @abstractmethod
    async def open(self, config: Optional[SessionConfig] = None) -> str:
        """
        يفتح جلسة حوارية منطقية جديدة.
        يعيد SessionID فريدًا. يبدأ عدادات TTL و Idle.
        """
        ...

    @abstractmethod
    async def close(self, session_id: str, reason: str = "normal") -> None:
        """
        ينهي الجلسة فورًا، يحرر الموارد، ويسجل سبب الإنهاء.
        أي محاولة استخدام لاحق للـ SessionID ترفع خطأ.
        """
        ...

    @abstractmethod
    async def refresh(self, session_id: str) -> bool:
        """
        يعيد ضبط عداد الخمول (Idle) ويطيل العمر الافتراضي إذا لزم.
        يعاد استدعاؤه مع كل نقل بيانات ناجح لضمان بقاء الجلسة مفتوحة.
        """
        ...

    @abstractmethod
    async def status(self, session_id: str) -> SessionStatus:
        """
        يعيد الحالة الحالية للجلسة (نشطة، خاملة، منتهية، مغلقة).
        """
        ...