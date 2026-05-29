# network/resilience/__init__.py
"""
OSI Layer 3 Resilience Patterns.
يوفر آليات تحمل الأعطال (Fault-Tolerance) لحماية توجيه الشبكة ومجمعات القنوات من الانهيار المتتالي.
"""
from __future__ import annotations

from .circuit_breaker import (
    AsyncCircuitBreaker,
    CircuitBreakerError,
    CircuitState,
)

__all__ = [
    "AsyncCircuitBreaker",
    "CircuitBreakerError",
    "CircuitState",
]