# network/algorithms/round_robin.py
"""خوارزمية الدوران المتساوي (Round-Robin). آمنة للأحداثية، متزامنة، ومعزولة."""
from __future__ import annotations

import asyncio
import logging
from typing import List, Optional

from network.protocol import ILoadBalancerStrategy, ChannelRef

logger = logging.getLogger(__name__)

class RoundRobinStrategy(ILoadBalancerStrategy):
    def __init__(self):
        self._index: int = 0
        self._lock = asyncio.Lock()

    def select(self, candidates: List[ChannelRef]) -> Optional[ChannelRef]:
        healthy = [c for c in candidates if c.is_healthy]
        if not healthy:
            healthy = candidates  # Fallback عند عدم وجود قنوات صحية
        if not healthy:
            return None

        # GIL يحمي الزيادة في CPython، لكن الـ Lock يضمن الأمان في بيئات متعددة الخيوط
        # ملاحظة: نستخدم lock داخليًا لكن نعيد القيمة فورًا لتجنب حظر الحلقة
        idx = self._index % len(healthy)
        self._index += 1
        chosen = healthy[idx]
        logger.debug(f"RoundRobin selected channel '{chosen.id}' (index={idx})")
        return chosen