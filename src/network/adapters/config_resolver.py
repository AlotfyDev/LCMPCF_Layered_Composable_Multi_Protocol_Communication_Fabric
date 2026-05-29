# network/adapters/config_resolver.py
"""
غلاف تكيفي لاكتشاف الخدمات عبر التكوين (YAML/ENV).
يعتمد على: pyyaml (تحليل تكوين ناضج), os.environ (حقن ديناميكي).
يحوّل ملفات التكوين الثابتة إلى قائمة نقاط نهاية قابلة للاستعلام.
"""
from __future__ import annotations

import os
import yaml
import logging
from pathlib import Path
from typing import Dict, List, Optional

from network.protocol import IServiceResolver, Endpoint

logger = logging.getLogger(__name__)


class ConfigServiceResolver(IServiceResolver):
    """محلل خدمات يعتمد على ملفات التكوين ومتغيرات البيئة."""

    def __init__(self, config_path: str = "transport_example.yaml"):
        self._config_path = config_path
        self._cache: Dict[str, List[Endpoint]] = {}
        self._load_config()

    def _load_config(self) -> None:
        path = Path(self._config_path)
        if not path.exists():
            logger.warning(f"Config resolver file not found: {path}")
            return

        with open(path, "r") as f:
            data = yaml.safe_load(f) or {}

        services = data.get("services", {})
        for svc_name, endpoints in services.items():
            resolved_endpoints = []
            for ep in endpoints if isinstance(endpoints, list) else [endpoints]:
                scheme = ep.get("scheme", "http")
                host = os.getenv(f"{svc_name.upper()}_HOST", ep.get("host", "127.0.0.1"))
                port = int(os.getenv(f"{svc_name.upper()}_PORT", ep.get("port", 80)))
                path_str = ep.get("path", "/")
                resolved_endpoints.append(Endpoint(scheme, host, port, path_str))
            self._cache[svc_name] = resolved_endpoints
        logger.info(f"Config resolver loaded {len(self._cache)} services")

    async def resolve(self, service_name: str, port: int = 0) -> List[Endpoint]:
        eps = self._cache.get(service_name, [])
        if port:
            return [e if e.port != port else Endpoint(e.scheme, e.host, port, e.path, e.metadata) for e in eps]
        return eps

    async def refresh(self) -> None:
        self._load_config()

    def list_services(self) -> List[str]:
        return list(self._cache.keys())


# Alias for factory import compatibility
ConfigResolver = ConfigServiceResolver