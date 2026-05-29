# network/algorithms/least_active.py
"""خوارزمية الأقل نشاطًا (Least-Active). تختار القناة ذات أقل جلسات نشطة."""
from __future__ import annotations

import logging
from typing import List, Optional

from network.protocol import ILoadBalancerStrategy, ChannelRef

logger = logging.getLogger(__name__)

class LeastActiveStrategy(ILoadBalancerStrategy):
    def select(self, candidates: List[ChannelRef]) -> Optional[ChannelRef]:
        healthy = [c for c in candidates if c.is_healthy]
        if not healthy:
            healthy = candidates
        if not healthy:
            return None

        # اختيار القناة ذات أقل active_sessions، مع كسر التعادل عشوائيًا أو بالأقدم
        chosen = min(healthy, key=lambda c: c.active_sessions)
        logger.debug(f"LeastActive selected channel '{chosen.id}' (sessions={chosen.active_sessions})")
        return chosen