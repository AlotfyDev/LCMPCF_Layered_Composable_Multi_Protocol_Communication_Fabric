# network/adapters/dns_resolver.py
"""
غلاف تكيفي لاكتشاف الخدمات عبر DNS.
يعتمد على: socket (مكتبة نظام ناضجة), asyncio (غير متزامن آمن).
يوفر دقة وكشف عناوين IP ديناميكي مع تخزين مؤقت ومؤقت انتهاء (TTL).
"""
from __future__ import annotations

import asyncio
import socket
import logging
import time
from typing import Dict, List, Tuple

from network.protocol import IServiceResolver, Endpoint

logger = logging.getLogger(__name__)


class StandardDnsResolver(IServiceResolver):
    """محلل خدمات يعتمد على DNS القياسي مع تخزين مؤقت وآمن للأحداثية."""

    def __init__(self, default_port: int = 80, cache_ttl: int = 60):
        self._default_port = default_port
        self._cache_ttl = cache_ttl
        self._cache: Dict[str, Tuple[List[Endpoint], float]] = {}

    async def resolve(self, service_name: str, port: int = 0) -> List[Endpoint]:
        target_port = port or self._default_port
        now = time.time()
        cached, cached_at = self._cache.get(service_name, ([], 0))

        if cached and (now - cached_at) < self._cache_ttl:
            return cached

        try:
            results = await asyncio.get_event_loop().run_in_executor(
                None, self._blocking_dns_lookup, service_name, target_port
            )
            self._cache[service_name] = (results, now)
            logger.debug(f"DNS resolved {service_name} -> {len(results)} endpoints")
            return results
        except Exception as e:
            logger.error(f"DNS resolution failed for {service_name}: {e}")
            return self._cache.get(service_name, ([], 0))[0]

    def _blocking_dns_lookup(self, host: str, port: int) -> List[Endpoint]:
        try:
            infos = socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
            return [
                Endpoint(scheme="tcp", host=info[4][0], port=info[4][1])
                for info in infos
            ]
        except socket.gaierror:
            return []

    async def refresh(self) -> None:
        self._cache.clear()
        logger.debug("DNS cache cleared")

    def list_services(self) -> List[str]:
        return list(self._cache.keys())


# Alias for factory import compatibility
DNSResolver = StandardDnsResolver
