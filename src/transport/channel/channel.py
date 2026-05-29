# transport/channel/channel.py
"""
التنفيذ المعياري للقناة (Channel Implementation).
يدير الحالة، دورة الحياة، المقاييس، والأمان المتزامن.
يفوض التسليم الفعلي لـ BaseTransporter، معزولًا تمامًا عن L7.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import AsyncIterator, Optional

from transport.base import BaseTransporter, DeliveryReport, TransportError, ErrorType
from transport.config import ChannelSettingsConfig
from transport.context import TransportContext
from transport.channel.protocol import IChannel
from transport.channel.types import ChannelState, ChannelError, ChannelMetrics

logger = logging.getLogger(__name__)


class Channel(IChannel):
    """
    غلاف معماري للقناة يطبق IChannel مع ضمان SRP و Encapsulation.
    لا ينفذ ترميزًا، لا يدير retry، ولا يفسر السياق. يركز حصريًا على:
    - انتقالات الحالة الآمنة (State-Safe Transitions)
    - إدارة دورة الحياة (Lifecycle Orchestration)
    - تتبع المقاييس (Metrics Tracking)
    - تفويض التسليم للناقل (Transport Delegation)
    """

    def __init__(self, config: ChannelSettingsConfig, transporter: BaseTransporter):
        self.config = config
        self.transporter = transporter
        self._state = ChannelState.CLOSED
        self._lock = asyncio.Lock()
        self._metrics = ChannelMetrics()

    @property
    def state(self) -> ChannelState:
        return self._state

    @property
    def metrics(self) -> ChannelMetrics:
        return self._metrics

    async def open(self, context: Optional[TransportContext] = None) -> None:
        async with self._lock:
            if self._state in (ChannelState.ACTIVE, ChannelState.CONNECTING):
                return
            if self._state == ChannelState.DRAINING:
                raise ChannelError("Cannot open a draining channel", self._state)

            self._state = ChannelState.CONNECTING
            try:
                # تفويض التهيئة للناقل (يدعم Lazy/Explicit Initialization)
                if hasattr(self.transporter, "_ensure_connection"):
                    await self.transporter._ensure_connection()
                
                self._state = ChannelState.ACTIVE
                self._metrics.opened_at = time.time()
                logger.debug(
                    f"Channel opened: state=ACTIVE, "
                    f"transporter={self.transporter.__class__.__name__}, "
                    f"config={self.config.__class__.__name__}"
                )
            except Exception as e:
                self._state = ChannelState.FAILED
                self._metrics.errors += 1
                logger.error(f"Channel open failed: {e}")
                raise ChannelError(f"Failed to initialize channel: {e}", self._state) from e

    async def close(self) -> None:
        async with self._lock:
            if self._state == ChannelState.CLOSED:
                return
            if self._state == ChannelState.DRAINING:
                return  # Idempotent graceful shutdown

            self._state = ChannelState.DRAINING
            try:
                await self.transporter.close()
                self._state = ChannelState.CLOSED
                self._metrics.closed_at = time.time()
                logger.debug(
                    f"Channel closed: state=CLOSED, "
                    f"transporter={self.transporter.__class__.__name__}, "
                    f"config={self.config.__class__.__name__}"
                )
            except Exception as e:
                self._state = ChannelState.FAILED
                self._metrics.errors += 1
                logger.error(f"Channel close failed: {e}")
                raise ChannelError(f"Failed to close channel: {e}", self._state) from e

    async def send(self, payload: bytes, context: TransportContext) -> DeliveryReport:
        await self._assert_active()
        try:
            report = await self.transporter.send(payload, context)
            if report.success:
                self._metrics.messages_sent += 1
                self._metrics.bytes_sent += report.bytes_sent
            return report
        except TransportError as e:
            self._metrics.errors += 1
            if e.error_type == ErrorType.PERMANENT:
                await self._transition_to_failed(e)
            raise

    async def stream(
        self, payload: bytes, context: TransportContext
    ) -> AsyncIterator[bytes]:
        await self._assert_active()
        try:
            async for chunk in self.transporter.stream(payload, context):
                yield chunk
        except TransportError as e:
            self._metrics.errors += 1
            if e.error_type == ErrorType.PERMANENT:
                await self._transition_to_failed(e)
            raise

    async def _assert_active(self) -> None:
        if self._state != ChannelState.ACTIVE:
            raise ChannelError(
                f"Channel is not active. Current state: {self._state.value}. Call open() first.",
                self._state
            )

    async def _transition_to_failed(self, error: Exception) -> None:
        async with self._lock:
            if self._state not in (ChannelState.FAILED, ChannelState.CLOSED):
                self._state = ChannelState.FAILED
                logger.warning(f"Channel transitioned to FAILED due to: {error}")

    # ── Context Manager Support ──────────────────────────────
    async def __aenter__(self) -> Channel:
        await self.open()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()