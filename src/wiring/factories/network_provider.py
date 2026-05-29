from __future__ import annotations

import logging
from typing import Optional

from network.protocol import IChannelPool, ISessionRouter, ILoadBalancerStrategy
from network.adapters.pool_adapter import AsyncChannelPool
from network.adapters.router_adapter import SessionRouterAdapter
from network.adapters.dns_resolver import DNSResolver
from network.adapters.config_resolver import ConfigResolver
from network.algorithms.round_robin import RoundRobinStrategy
from network.algorithms.least_active import LeastActiveStrategy
from network.resilience.circuit_breaker import AsyncCircuitBreaker
from transport.config import TransportConfig

logger = logging.getLogger(__name__)


def build_channel_pool(
    config: TransportConfig,
    max_size: int = 50,
    idle_timeout: float = 120.0,
) -> IChannelPool:
    """يبني مجمع قنوات (L3 Channel Pool) ready للاستخدام."""
    pool = AsyncChannelPool(
        config=config,
        max_size=max_size,
        idle_timeout=idle_timeout,
    )
    logger.info(f"ChannelPool built: max_size={max_size}, idle_timeout={idle_timeout}s")
    return pool


def build_load_balancer(strategy_name: str = "round_robin") -> ILoadBalancerStrategy:
    """يبني خوارزمية موازنة التحميل حسب الاسم."""
    if strategy_name == "round_robin":
        return RoundRobinStrategy()
    elif strategy_name == "least_active":
        return LeastActiveStrategy()
    else:
        logger.warning(f"Unknown strategy '{strategy_name}', falling back to round_robin")
        return RoundRobinStrategy()


def build_session_router(
    strategy: ILoadBalancerStrategy,
    channel_lookup=None,
) -> ISessionRouter:
    """يبني موجه جلسات L3 مع الخوارزمية المحقونة."""
    if channel_lookup is None:
        channel_lookup = lambda _: None
    router = SessionRouterAdapter(strategy=strategy, channel_lookup=channel_lookup)
    logger.info(f"SessionRouterAdapter built with {strategy.__class__.__name__}")
    return router


def build_circuit_breaker(
    failure_threshold: int = 5,
    recovery_timeout: float = 30.0,
    success_threshold: int = 2,
) -> AsyncCircuitBreaker:
    """يبني قاطع دائرة مع التكوين المحدد."""
    cb = AsyncCircuitBreaker(
        failure_threshold=failure_threshold,
        recovery_timeout=recovery_timeout,
        success_threshold=success_threshold,
    )
    logger.info(f"CircuitBreaker built: threshold={failure_threshold}, recovery={recovery_timeout}s")
    return cb
