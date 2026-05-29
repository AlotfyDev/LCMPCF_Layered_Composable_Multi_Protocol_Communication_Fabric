# contracts/communication_gateway.py
"""
Abstract Communication Gateway Contract.
يحدد الواجهة الدنيا التي تستهلكها المكونات التطبيقية (BaseActor, Adapters, CLI)
للتفاعل مع مركّب الاتصالات دون اقتران بالطبقات الداخلية (L3-L7).

✅ يعتمد على typing.Protocol للربط البنيوي (Structural Subtyping)
✅ Async-Aware بالكامل
✅ لا يكشف تفاصيل التنفيذ، السجلات، أو الباييبلاينز
"""
from __future__ import annotations

from typing import Any, AsyncIterator, Dict, Optional, Protocol

class ICommunicationGateway(Protocol):
    async def send(
        self,
        payload: Any,
        protocol: str = "http",
        session_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        stream: bool = False,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Any: ...

    async def receive(
        self,
        raw_bytes: bytes,
        protocol: str = "http",
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
        channel_ref: Optional[str] = None
    ) -> Any: ...

    async def receive_stream(
        self,
        byte_stream: AsyncIterator[bytes],
        protocol: str = "http",
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None
    ) -> AsyncIterator[Any]: ...

    async def close_session(self, session_id: str, protocol: str = "http") -> None: ...

    async def health_check(self) -> Dict[str, Any]: ...