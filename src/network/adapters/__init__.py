# network/adapters/__init__.py
"""
حزمة أدابترز طبقة الشبكة.
تعرض غلافات تكيفية لمكتبات ناضجة (asyncio, yaml, socket) تحت عقود مجردة موحدة.
"""
from .pool_adapter import AsyncChannelPool
from .config_resolver import ConfigServiceResolver
from .dns_resolver import StandardDnsResolver

__all__ = [
    "AsyncChannelPool",
    "ConfigServiceResolver",
    "StandardDnsResolver",
]