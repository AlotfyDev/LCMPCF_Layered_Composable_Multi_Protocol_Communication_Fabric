from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

from transport.base import Direction
from transport.channel import Channel
from transport.channel.protocol import IChannel
from presentation.pipeline import PresentationPipeline
from protocols.protocol import IProtocolHandler
from protocols.http_handler import HttpProtocolHandler
from protocols.cli_handler import CliProtocolHandler
from protocols.grpc_handler import GrpcProtocolHandler
from protocols.graphql_handler import GraphQLProtocolHandler
from protocols.webhook_handler import WebhookProtocolHandler
from protocols.local_ipc_handler import LocalIpcProtocolHandler
from protocols.inprocess_handler import InProcessProtocolHandler
from wiring.config.loader import ProtocolEntryConfig

logger = logging.getLogger(__name__)


def build_protocol_handler(
    entry: ProtocolEntryConfig,
    channel: IChannel,
    pipeline: PresentationPipeline,
    direction: Direction = Direction.OUTBOUND,
    base_url: str = "",
    target: Optional[Callable] = None,
) -> IProtocolHandler:
    """يبني معالج بروتوكول L7 حسب التكوين.

    Args:
        entry: تكوين البروتوكول من YAML
        channel: قناة L4 للحقن في المعالج
        pipeline: خط عرض L6 للحقن
        direction: اتجاه المعالج
        base_url: URL أساسي (لـ HTTP/gRPC)
        target: دالة هدف (لـ InProcess)

    Returns:
        IProtocolHandler جاهز للاستخدام.

    Raises:
        ValueError: إذا كان نوع البروتوكول غير معروف
    """
    name = entry.name.lower()

    if name == "http":
        return HttpProtocolHandler(
            channel=channel,
            pipeline=pipeline,
            base_url=base_url or entry.endpoint or "",
            direction=direction,
        )
    elif name == "cli":
        return CliProtocolHandler(
            channel=channel,
            pipeline=pipeline,
            direction=direction,
        )
    elif name == "grpc":
        return GrpcProtocolHandler(
            channel=channel,
            pipeline=pipeline,
            target=entry.endpoint or "",
            direction=direction,
        )
    elif name == "graphql":
        return GraphQLProtocolHandler(
            pipeline=pipeline,
            direction=direction,
        )
    elif name == "webhook":
        return WebhookProtocolHandler(
            pipeline=pipeline,
            direction=direction,
            shared_secret=entry.endpoint if entry.endpoint and len(entry.endpoint) > 10 else None,
        )
    elif name == "local_ipc":
        return LocalIpcProtocolHandler(
            channel=channel,
            pipeline=pipeline,
            ipc_path=entry.socket_path,
            direction=direction,
        )
    elif name == "inprocess":
        return InProcessProtocolHandler(
            target=target,
            pipeline=pipeline,
        )
    else:
        raise ValueError(f"Unknown protocol handler: '{name}'")


def build_all_protocol_handlers(
    protocol_configs: Dict[str, ProtocolEntryConfig],
    channels: Dict[str, IChannel],
    outbound_pipeline: PresentationPipeline,
    inbound_pipeline: PresentationPipeline,
    default_target: Optional[Callable] = None,
) -> Dict[str, IProtocolHandler]:
    """يبني جميع معالجات البروتوكول حسب التكوين.

    Args:
        protocol_configs: قاموس تكوينات البروتوكول
        channels: قاموس القنوات لكل بروتوكول
        outbound_pipeline: خط L6 للصادر
        inbound_pipeline: خط L6 للوارد
        default_target: دالة هدف افتراضية (لـ InProcess)

    Returns:
        قاموس {protocol_name: IProtocolHandler}
    """
    handlers: Dict[str, IProtocolHandler] = {}

    for name, entry in protocol_configs.items():
        channel = channels.get(name)
        if not channel:
            logger.warning(f"No channel provided for protocol '{name}', using inprocess fallback")
            channel = channels.get("_default")

        dir_enum = Direction.OUTBOUND if entry.direction == "outbound" else Direction.INBOUND
        pipeline = outbound_pipeline if dir_enum == Direction.OUTBOUND else inbound_pipeline

        try:
            handler = build_protocol_handler(
                entry=entry,
                channel=channel,
                pipeline=pipeline,
                direction=dir_enum,
                base_url=entry.endpoint or "",
                target=default_target,
            )
            handlers[name] = handler
            logger.info(f"Protocol handler '{name}' built ({entry.direction}/{entry.transport})")
        except Exception as e:
            logger.error(f"Failed to build protocol handler '{name}': {e}")

    return handlers
