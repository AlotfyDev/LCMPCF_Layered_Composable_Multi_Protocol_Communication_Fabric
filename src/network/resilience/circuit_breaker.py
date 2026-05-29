# network/resilience/circuit_breaker.py
"""نمط قاطع الدائرة (Circuit Breaker). يحمي طبقة الشبكة من الانهيار المتتالي."""
from __future__ import annotations

import asyncio
import logging
import time
from enum import Enum
from typing import Any, Callable, Awaitable, Optional

logger = logging.getLogger(__name__)

class CircuitState(Enum):
    CLOSED = "closed"       # طبيعي، يسمح بالطلبات
    OPEN = "open"           # معطل، يرفض الطلبات فورًا
    HALF_OPEN = "half_open" # اختباري، يسمح بطلب واحد للاستكشاف

class CircuitBreakerError(Exception):
    """يُرفع عندما يكون القاطع في حالة OPEN."""
    pass

class AsyncCircuitBreaker:
    """قاطع دائرة غير متزامن يحيط بأي دالة/كوروتين شبكية (مثل acquire/resolve)."""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        success_threshold: int = 2
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold
        
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        return self._state

    async def call(self, func: Callable[..., Awaitable[Any]], *args, **kwargs) -> Any:
        """يغلف الاستدعاء بحماية قاطع الدائرة."""
        async with self._lock:
            self._check_state_transition()
            if self._state == CircuitState.OPEN:
                raise CircuitBreakerError(f"Circuit is OPEN. Retry after {self.recovery_timeout}s")

        try:
            result = await func(*args, **kwargs)
            await self._record_success()
            return result
        except Exception as e:
            await self._record_failure()
            raise

    def _check_state_transition(self) -> None:
        """ينتقل من OPEN إلى HALF_OPEN بعد انتهاء مهلة الاستعادة."""
        if self._state == CircuitState.OPEN and self._last_failure_time:
            if time.time() - self._last_failure_time >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._success_count = 0
                logger.info("Circuit Breaker transitioned to HALF_OPEN")

    async def _record_success(self) -> None:
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    logger.info("Circuit Breaker CLOSED after successful recovery")
            else:
                self._failure_count = max(0, self._failure_count - 1)

    async def _record_failure(self) -> None:
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning("Circuit Breaker OPEN (HALF_OPEN failed)")
            elif self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(f"Circuit Breaker OPEN after {self._failure_count} failures")