# transport/channel/protocol.py
"""
عقد القناة المجردة (IChannel Protocol).
يحدد واجهة موحدة وآمنة لإدارة القناة دون كشف تفاصيل الناقل أو التكوين.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional
from transport.context import TransportContext
from transport.base import DeliveryReport
from transport.channel.types import ChannelState, ChannelMetrics


class IChannel(ABC):
    """
    البروتوكول المعياري لإدارة قنوات النقل (OSI L4 Channel Contract).
    يطبق مبدأ Dependency Inversion: المستهلكون يعتمدون على هذه الواجهة،
    وليس على التنفيذ الملموس أو إعدادات القناة.
    """
    
    @property
    @abstractmethod
    def state(self) -> ChannelState:
        """الحالة الحالية للقناة."""
        ...

    @property
    @abstractmethod
    def metrics(self) -> ChannelMetrics:
        """مقاييس الأداء والاستهلاك."""
        ...

    @abstractmethod
    async def open(self, context: Optional[TransportContext] = None) -> None:
        """تهيئة القناة والانتقال إلى الحالة ACTIVE. آمن للاستدعاء المتكرر."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """إغلاق القناة بأمان والانتقال إلى الحالة CLOSED."""
        ...

    @abstractmethod
    async def send(self, payload: bytes, context: TransportContext) -> DeliveryReport:
        """إرسال حمولة بايتات مع ضمان الحالة النشطة."""
        ...

    @abstractmethod
    async def stream(
        self, payload: bytes, context: TransportContext
    ) -> AsyncIterator[bytes]:
        """بث حمولة متدفقة مع ضمان الحالة النشطة."""
        ...