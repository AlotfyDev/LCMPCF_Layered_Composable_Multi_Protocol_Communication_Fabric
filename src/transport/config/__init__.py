# transport/config/__init__.py
"""
تكوينات الطبقة الرابعة (L4 Transport Configuration).
نماذج Pydantic جامدة وقابلة للتسلسل، مصممة للحقن في TransportFactory
لربط الناقل، سياسات إعادة المحاولة، وافتراضات سياق الجلسة.
"""
from .transport_config import (
    TransportConfig,
    TransportType,
    RetryPolicyConfig,
    ContextDefaultsConfig,
    ChannelSettingsConfig,
)

__all__ = [
    "TransportConfig",
    "TransportType",
    "RetryPolicyConfig",
    "ContextDefaultsConfig",
    "ChannelSettingsConfig",
]