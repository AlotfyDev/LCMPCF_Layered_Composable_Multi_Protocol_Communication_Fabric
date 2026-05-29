# transport/channel/__init__.py
"""
OSI Layer 4 Channel Module.
يعرض واجهة القناة المجردة، التنفيذ المعياري، وأنواع الحالة/الأخطاء.
يضمن فصل إدارة دورة الحياة عن آلية النقل الصرفة.
"""
from .protocol import IChannel
from .channel import Channel
from .types import ChannelState, ChannelError, ChannelMetrics

__all__ = ["IChannel", "Channel", "ChannelState", "ChannelError", "ChannelMetrics"]