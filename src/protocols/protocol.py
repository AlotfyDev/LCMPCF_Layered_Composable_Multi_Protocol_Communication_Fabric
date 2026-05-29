from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Optional

from transport.context import TransportContext


class IProtocolHandler(ABC):
    """
    OSI Layer 7 Application Protocol Handler Contract.
    يحدد العقد المشترك لجميع معالجات البروتوكولات التطبيقية (HTTP, CLI, gRPC, GraphQL,
    Webhooks, Local IPC, InProcess).

    يوحد واجهتي الإرسال (outbound) والاستقبال (inbound) مع العزل التام:
    - لا يعرف طبقات L3-L5 (Network, Session, Transport)
    - يعتمد على TransportContext فقط لتمرير بيانات السياق
    - يفوض الترميز/الضغط لـ L6 PresentationPipeline
    """

    @abstractmethod
    async def prepare_outbound(self, payload: Any, ctx: TransportContext) -> Any:
        ...

    @abstractmethod
    async def process_inbound(self, app_obj: Any, ctx: TransportContext) -> Any:
        ...

    @abstractmethod
    async def process_outbound_response(self, decoded: Any, ctx: TransportContext) -> Any:
        ...

    @abstractmethod
    async def close(self) -> None:
        ...
