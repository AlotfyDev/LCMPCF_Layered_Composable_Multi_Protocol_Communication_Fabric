from __future__ import annotations

import logging
from typing import Optional

from transport.config import TransportConfig, TransportType
from transport.factory import TransportFactory, TransportFactoryError
from transport.context import RetryHook
from transport.channel.protocol import IChannel

logger = logging.getLogger(__name__)


def build_channel(
    config: TransportConfig,
    retry_hook: Optional[RetryHook] = None,
) -> IChannel:
    """
    يبني قناة نقل L4 كاملة (مغلّفة بـ Channel مع إدارة الحالة).
    """
    if not isinstance(config, TransportConfig):
        raise TransportFactoryError("config must be an instance of TransportConfig")
    channel = TransportFactory.create_channel(config=config, retry_hook=retry_hook)
    logger.info(
        f"L4 Channel built: type={config.transport_type.value}, "
        f"dir={config.direction}"
    )
    return channel


def build_transport_config_from_protocol(
    protocol_name: str,
    transport_type: str = "inprocess",
    direction: str = "outbound",
    endpoint: Optional[str] = None,
    port: Optional[int] = None,
    socket_path: Optional[str] = None,
) -> TransportConfig:
    """يجسّر تكوين البروتوكول إلى TransportConfig لطبقة L4.

    Args:
        protocol_name: اسم البروتوكول (للتوثيق فقط)
        transport_type: نوع النقل (tcp, uds, inprocess, cli, websocket)
        direction: outbound أو inbound
        endpoint: نقطة النهاية (لـ TCP/HTTP/WS)
        port: المنفذ
        socket_path: مسار المقبس (لـ UDS)

    Returns:
        TransportConfig جاهز للحقن في TransportFactory
    """
    ttype = TransportType(transport_type) if isinstance(transport_type, str) else transport_type

    # بناء config مع المعطيات المتوفرة
    from transport.config import TransportConfig, ChannelSettingsConfig, RetryPolicyConfig

    channel_cfg = ChannelSettingsConfig()
    if endpoint:
        channel_cfg.endpoint_url = endpoint
    if port:
        channel_cfg.port = port
    if socket_path:
        channel_cfg.socket_path = socket_path

    config = TransportConfig(
        transport_type=ttype,
        direction=direction,
        channel=channel_cfg,
    )
    logger.debug(f"TransportConfig built for '{protocol_name}': {ttype.value}/{direction}")
    return config
