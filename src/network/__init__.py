# network/__init__.py
"""
OSI Layer 3 Network & Routing Orchestration.
واجهة عامة موحدة لإدارة المجموعات، التوجيه، اكتشاف الخدمات، خوارزميات التوازن، وأنماط المرونة.
تعمل كطبقة تنسيق تركيبي (Composable Orchestration) تربط L4/L5 بالعالم الخارجي عبر عقود مجردة وأدابترز قابلة للتبديل.
"""
from __future__ import annotations

# 📜 العقود المجردة (Contracts)
from .protocol import (
    IChannelPool,
    ISessionRouter,
    IServiceResolver,
    ILoadBalancerStrategy,
    Endpoint,
    ChannelRef,
)

# 🔌 الأدابترز (Adapters - تغليف حلول ناضجة)
from .adapters.pool_adapter import AsyncChannelPool
from .adapters.router_adapter import SessionRouterAdapter
from .adapters.config_resolver import ConfigServiceResolver
from .adapters.dns_resolver import StandardDnsResolver

# ⚖️ الخوارزميات (Algorithms - قابلة للاستبدال الديناميكي)
from .algorithms.round_robin import RoundRobinStrategy
from .algorithms.least_active import LeastActiveStrategy

# 🛡️ أنماط المرونة (Resilience Patterns)
from .resilience import (
    AsyncCircuitBreaker,
    CircuitBreakerError,
    CircuitState,
)

__all__ = [
    # 📜 Contracts
    "IChannelPool",
    "ISessionRouter",
    "IServiceResolver",
    "ILoadBalancerStrategy",
    "Endpoint",
    "ChannelRef",
    
    # 🔌 Adapters
    "AsyncChannelPool",
    "SessionRouterAdapter",
    "ConfigServiceResolver",
    "StandardDnsResolver",
    
    # ⚖️ Algorithms
    "RoundRobinStrategy",
    "LeastActiveStrategy",
    
    # 🛡️ Resilience
    "AsyncCircuitBreaker",
    "CircuitBreakerError",
    "CircuitState",
]