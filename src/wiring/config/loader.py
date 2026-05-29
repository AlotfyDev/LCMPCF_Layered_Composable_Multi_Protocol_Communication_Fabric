from __future__ import annotations

import os
import yaml
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from transport.config import TransportConfig, TransportType, RetryPolicyConfig, ContextDefaultsConfig, ChannelSettingsConfig

logger = logging.getLogger(__name__)


@dataclass
class NetworkConfig:
    pool_max_size: int = 50
    pool_idle_timeout: float = 120.0
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_recovery_timeout: float = 30.0
    circuit_breaker_success_threshold: int = 2
    load_balancer_strategy: str = "round_robin"


@dataclass
class SessionConfig:
    default_ttl: float = 3600.0
    idle_timeout: float = 300.0
    eviction_interval: float = 60.0
    max_failover_attempts: int = 3
    failover_delay: float = 1.0
    checkpoint_enabled: bool = False


@dataclass
class PresentationConfig:
    serializer: str = "json"
    compressor: str = "gzip"
    min_compression_bytes: int = 1024
    auto_detect_compression: bool = True
    bypass_inprocess: bool = True


@dataclass
class ProtocolEntryConfig:
    name: str
    transport: str
    direction: str = "outbound"
    endpoint: Optional[str] = None
    port: Optional[int] = None
    socket_path: Optional[str] = None


@dataclass
class ProtocolConfig:
    handlers: Dict[str, ProtocolEntryConfig] = field(default_factory=dict)


@dataclass
class AppConfig:
    network: NetworkConfig = field(default_factory=NetworkConfig)
    session: SessionConfig = field(default_factory=SessionConfig)
    presentation: PresentationConfig = field(default_factory=PresentationConfig)
    protocols: Dict[str, ProtocolEntryConfig] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)


def load_config(config_path: str) -> AppConfig:
    """يقرأ ملف YAML للتكوين ويعيد AppConfig محمّلًا بالقيم.”

    Args:
        config_path: مسار ملف YAML

    Returns:
        AppConfig: التكوين المحمّل مع القيم الافتراضية
    """
    resolved_path = _resolve_path(config_path)
    if not resolved_path or not os.path.exists(resolved_path):
        logger.warning(f"Config file '{config_path}' not found. Using defaults.")
        return AppConfig()

    with open(resolved_path, "r") as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        logger.warning("Config file empty or invalid. Using defaults.")
        return AppConfig()

    cfg = AppConfig(raw=raw)

    # Network section
    net = raw.get("network", {})
    if net:
        cfg.network = NetworkConfig(
            pool_max_size=net.get("pool_max_size", 50),
            pool_idle_timeout=net.get("pool_idle_timeout", 120.0),
            circuit_breaker_failure_threshold=net.get("circuit_breaker_failure_threshold", 5),
            circuit_breaker_recovery_timeout=net.get("circuit_breaker_recovery_timeout", 30.0),
            circuit_breaker_success_threshold=net.get("circuit_breaker_success_threshold", 2),
            load_balancer_strategy=net.get("load_balancer_strategy", "round_robin"),
        )

    # Session section
    sess = raw.get("session", {})
    if sess:
        cfg.session = SessionConfig(
            default_ttl=sess.get("default_ttl", 3600.0),
            idle_timeout=sess.get("idle_timeout", 300.0),
            eviction_interval=sess.get("eviction_interval", 60.0),
            max_failover_attempts=sess.get("max_failover_attempts", 3),
            failover_delay=sess.get("failover_delay", 1.0),
            checkpoint_enabled=sess.get("checkpoint_enabled", False),
        )

    # Presentation section
    pres = raw.get("presentation", {})
    if pres:
        cfg.presentation = PresentationConfig(
            serializer=pres.get("serializer", "json"),
            compressor=pres.get("compressor", "gzip"),
            min_compression_bytes=pres.get("min_compression_bytes", 1024),
            auto_detect_compression=pres.get("auto_detect_compression", True),
            bypass_inprocess=pres.get("bypass_inprocess", True),
        )

    # Protocols section
    prots = raw.get("protocols", {})
    for name, pdata in prots.items():
        if isinstance(pdata, dict):
            cfg.protocols[name] = ProtocolEntryConfig(
                name=name,
                transport=pdata.get("transport", "inprocess"),
                direction=pdata.get("direction", "outbound"),
                endpoint=pdata.get("endpoint"),
                port=pdata.get("port"),
                socket_path=pdata.get("socket_path"),
            )

    logger.info(f"Config loaded from '{config_path}': {len(cfg.protocols)} protocol(s), {len(raw)} section(s)")
    return cfg


def _resolve_path(config_path: str) -> Optional[str]:
    """يبحث عن ملف التكوين في المسارات الممكنة."""
    candidates = [
        config_path,
        os.path.join("config", config_path),
        os.path.join(os.path.dirname(__file__), config_path),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None
