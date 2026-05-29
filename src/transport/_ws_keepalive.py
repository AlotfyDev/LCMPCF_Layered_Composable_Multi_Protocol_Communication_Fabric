# transport/_ws_keepalive.py
"""
OSI L4 WebSocket Keep-Alive Policy (Ping/Pong Heartbeat).
مسؤوليته حصريًا: كشف الانقطاعات الصامتة (Silent Drop) وإدارة صحة القناة.
يعتمد على WSFramingEngine لتوليد إطارات التحكم.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional, Callable, Awaitable
from transport._ws_framing import WSFramingEngine, OP_PING, OP_PONG

logger = logging.getLogger(__name__)

class WSKeepAlivePolicy:
    def __init__(
        self,
        ping_interval: float = 30.0,
        pong_timeout: float = 10.0,
        max_missed: int = 3
    ):
        self.ping_interval = ping_interval
        self.pong_timeout = pong_timeout
        self.max_missed = max_missed
        self._task: Optional[asyncio.Task] = None
        self._pong_received = asyncio.Event()
        self._missed_count = 0
        self._on_timeout: Optional[Callable[[], Awaitable[None]]] = None
        self._writer: Optional[asyncio.StreamWriter] = None

    def start(
        self,
        writer: asyncio.StreamWriter,
        on_timeout_callback: Optional[Callable[[], Awaitable[None]]] = None
    ) -> None:
        if self._task and not self._task.done():
            logger.warning("Keep-alive already running")
            return
        self._writer = writer
        self._on_timeout = on_timeout_callback
        self._task = asyncio.create_task(self._ping_loop())
        logger.debug(f"WS Keep-Alive started: interval={self.ping_interval}s")

    def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                self._task.result()
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.debug("WS Keep-Alive stopped")

    def handle_pong(self) -> None:
        """يُستدعى عند استقبال إطار PONG لإبطال المهلة"""
        self._missed_count = 0
        self._pong_received.set()

    async def _ping_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self.ping_interval)
                if not self._writer or self._writer.is_closing():
                    break
                    
                ping_frame = WSFramingEngine.encode_frame(b"ping", opcode=OP_PING, mask=True)
                self._writer.write(ping_frame)
                await self._writer.drain()
                
                self._pong_received.clear()
                try:
                    await asyncio.wait_for(self._pong_received.wait(), timeout=self.pong_timeout)
                except asyncio.TimeoutError:
                    self._missed_count += 1
                    logger.warning(f"WS Pong timeout ({self._missed_count}/{self.max_missed})")
                    if self._missed_count >= self.max_missed:
                        logger.error("WS Keep-Alive: max missed reached, triggering timeout callback")
                        if self._on_timeout:
                            await self._on_timeout()
                        break
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"WS Keep-Alive error: {e}")
                break