# network/protocol.py
"""
OSI Layer 3 Network Contracts (Abstract Orchestration Interfaces).
يحدد عقود إدارة المجموعات، التوجيه، واكتشاف الخدمات.
لا يعتمد على أي تنفيذ محدد، ويصمم ليتم تكيّفه مع مكتبات ناضجة.
"""
from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Protocol, Any

from transport.channel.protocol import IChannel

# network/protocol.py (جزء مُضاف فقط)
from typing import List, Optional, Protocol
from dataclasses import dataclass, field

# ... (Endpoint, ChannelRef, IChannelPool, ISessionRouter, IServiceResolver كما هي)

class ILoadBalancerStrategy(Protocol):
    """عقد خوارزمية اختيار القناة. نقية، خالية من الحالة الشبكية، وقابلة للاختبار."""
    def select(self, candidates: List[ChannelRef]) -> Optional[ChannelRef]: ...

@dataclass(frozen=True)
class Endpoint:
    """نقطة نهاية خدمة قابلة للتوجيه."""
    scheme: str
    host: str
    port: int
    path: str = "/"
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def uri(self) -> str:
        return f"{self.scheme}://{self.host}:{self.port}{self.path}"


@dataclass(frozen=True)
class ChannelRef:
    """مرجع قناة قابل للاختيار والتوجيه."""
    id: str
    endpoint: Endpoint
    weight: float = 1.0
    active_sessions: int = 0
    is_healthy: bool = True


class IChannelPool(Protocol):
    """عقد إدارة مجموعة قنوات (Resource Pooling & Lifecycle)."""
    @abstractmethod
    async def acquire(self) -> IChannel: ...
    @abstractmethod
    async def release(self, channel: IChannel) -> None: ...
    @abstractmethod
    async def health_check(self) -> None: ...
    @abstractmethod
    async def close(self) -> None: ...


class ISessionRouter(Protocol):
    """عقد توجيه الجلسات وربطها بالقنوات (Routing & Binding)."""
    @abstractmethod
    def bind(self, session_id: str, channel_ref: ChannelRef) -> None: ...
    @abstractmethod
    def unbind(self, session_id: str) -> None: ...
    @abstractmethod
    async def resolve(self, session_id: str) -> Optional[IChannel]: ...
    @abstractmethod
    def select(self, candidates: List[ChannelRef]) -> Optional[ChannelRef]: ...


class IServiceResolver(Protocol):
    """عقد اكتشاف الخدمات وحل العناوين (Service Discovery)."""
    @abstractmethod
    async def resolve(self, service_name: str, port: int = 0) -> List[Endpoint]: ...
    @abstractmethod
    async def refresh(self) -> None: ...
    @abstractmethod
    def list_services(self) -> List[str]: ...
 