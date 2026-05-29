# network/adapters/pool_adapter.py
"""
غلاف تكيفي لمجمع القنوات (Channel Pool Adapter).
يعتمد على: asyncio.Queue (إدارة طوابير آمنة), TransportFactory (إنشاء قنوات),
ويتجنب إعادة اختراع الـ Pooling عبر استخدام أنماط بايثون القياسية الموثوقة.
"""
from __future__ import annotations

import asyncio
import logging
import time
import weakref
from typing import Dict, Optional

from transport.channel.protocol import IChannel
from transport.channel.types import ChannelState
from transport.factory import TransportFactory
from transport.config import TransportConfig
from network.protocol import IChannelPool

logger = logging.getLogger(__name__)


class AsyncChannelPool(IChannelPool):
    """مجمع قنوات غير متزامن يدير الاستعارة، الإفراج، والفحص الصحي."""

    def __init__(
        self,
        config: TransportConfig,
        max_size: int = 50,
        idle_timeout: float = 120.0
    ):
        self._config = config
        self._queue: asyncio.Queue[IChannel] = asyncio.Queue(maxsize=max_size)
        self._idle_timeout = idle_timeout
        self._factory = TransportFactory()
        self._usage_timestamps: Dict[int, float] = {}
        self._closed = False

    async def acquire(self) -> IChannel:
        if self._closed:
            raise RuntimeError("Pool is closed")
        try:
            ch = self._queue.get_nowait()
            self._usage_timestamps[id(ch)] = time.time()
            logger.debug(f"Channel acquired from pool: {id(ch)}")
            return ch
        except asyncio.QueueEmpty:
            ch = await self._factory.create_channel(self._config)
            await ch.open()
            self._usage_timestamps[id(ch)] = time.time()
            logger.debug(f"New channel created and acquired: {id(ch)}")
            return ch

    async def release(self, channel: IChannel) -> None:
        if self._closed or channel.state == ChannelState.FAILED:
            await channel.close()
            logger.warning(f"Unhealthy channel discarded: {id(channel)}")
            return

        if channel.state in (ChannelState.ACTIVE, ChannelState.CLOSED):
            await self._queue.put(channel)
            self._usage_timestamps[id(channel)] = time.time()
            logger.debug(f"Channel released to pool: {id(channel)}")
        else:
            await channel.close()

    async def health_check(self) -> None:
        """يفحص القنوات الخاملة ويغلقها بعد تجاوز المهلة."""
        now = time.time()
        stale_ids = [
            ch_id for ch_id, last_used in self._usage_timestamps.items()
            if now - last_used > self._idle_timeout
        ]
        if not stale_ids:
            return

        cleaned = 0
        while not self._queue.empty():
            ch = await self._queue.get()
            if id(ch) in stale_ids:
                await ch.close()
                cleaned += 1
                logger.debug(f"Idle channel closed during health check: {id(ch)}")
            else:
                await self._queue.put(ch)
        logger.info(f"Pool health check complete. Cleaned {cleaned} idle channels.")

    async def close(self) -> None:
        self._closed = True
        while not self._queue.empty():
            ch = await self._queue.get()
            await ch.close()
        self._usage_timestamps.clear()
        logger.info("ChannelPool closed and resources released.")