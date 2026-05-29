# network/adapters/router_adapter.py
"""أدابتر توجيه الجلسات. رفيع، يفوض الاختيار للخوارزمية، ويدير الربط فقط."""
from __future__ import annotations

import logging
from typing import Callable, Dict, List, Optional

from transport.channel.protocol import IChannel
from network.protocol import ISessionRouter, ILoadBalancerStrategy, ChannelRef

logger = logging.getLogger(__name__)

class SessionRouterAdapter(ISessionRouter):
    def __init__(
        self,
        strategy: ILoadBalancerStrategy,
        channel_lookup: Callable[[str], Optional[IChannel]]
    ):
        self._strategy = strategy
        self._channel_lookup = channel_lookup
        self._session_map: Dict[str, ChannelRef] = {}

    def bind(self, session_id: str, channel_ref: ChannelRef) -> None:
        self._session_map[session_id] = channel_ref
        logger.debug(f"Session '{session_id}' bound to channel '{channel_ref.id}'")

    def unbind(self, session_id: str) -> None:
        removed = self._session_map.pop(session_id, None)
        if removed:
            logger.debug(f"Session '{session_id}' unbound from channel '{removed.id}'")

    async def resolve(self, session_id: str) -> Optional[IChannel]:
        ref = self._session_map.get(session_id)
        if not ref:
            return None
        
        channel = self._channel_lookup(ref.id)
        if channel and channel.state.value in ("active", "connecting"):
            return channel
        
        logger.warning(f"Session '{session_id}' resolved but channel '{ref.id}' is unavailable")
        self._session_map.pop(session_id, None)  # تنظيف تلقائي للقناة التالفة
        return None

    def select(self, candidates: List[ChannelRef]) -> Optional[ChannelRef]:
        """يفوض اختيار القناة للخوارزمية المحقنة."""
        return self._strategy.select(candidates)