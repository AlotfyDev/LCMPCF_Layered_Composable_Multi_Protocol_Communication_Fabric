from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from session.session_registry import SessionRegistry
from session.session_dispatcher import SessionDispatcher
from session.coordinator import SessionCoordinator
from session.ICheckpointSync import ICheckpointSync
from network.protocol import IChannelPool, ISessionRouter

logger = logging.getLogger(__name__)


def build_session_registry(
    default_ttl: float = 3600.0,
    idle_timeout: float = 300.0,
    checkpoint_sync: Optional[ICheckpointSync] = None,
    eviction_interval: float = 60.0,
) -> SessionRegistry:
    """يبني سجل الجلسات مع TTL وإدارة الخمول."""
    registry = SessionRegistry(
        default_ttl=default_ttl,
        idle_timeout=idle_timeout,
        checkpoint_sync=checkpoint_sync,
        eviction_interval=eviction_interval,
    )
    logger.info(
        f"SessionRegistry built: TTL={default_ttl}s, idle={idle_timeout}s, "
        f"checkpoint={'enabled' if checkpoint_sync else 'disabled'}"
    )
    return registry


def build_session_dispatcher(
    registry: SessionRegistry,
    pool: IChannelPool,
    router: ISessionRouter,
    max_failover_attempts: int = 3,
    failover_delay: float = 1.0,
) -> SessionDispatcher:
    """يبني موزع الجلسات الذي يربط L5 بـ L3/L4."""
    dispatcher = SessionDispatcher(
        registry=registry,
        pool=pool,
        router=router,
        max_failover_attempts=max_failover_attempts,
        failover_delay=failover_delay,
    )
    logger.info(f"SessionDispatcher built: max_failover={max_failover_attempts}, delay={failover_delay}s")
    return dispatcher
