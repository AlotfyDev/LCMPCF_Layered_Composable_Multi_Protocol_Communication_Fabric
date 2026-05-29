# transport/context/__init__.py
"""
عقود السياق والسياسات التابعة للطبقة الرابعة (L4 Transport Dependencies).
يُعرّف أنواع البيانات الشفافة وبروتوكولات الخطافات التي تُمكّن L5 من إدارة الجلسة
دون كسر عزل الطبقة الرابعة أو اقترانها بمنطق المجال.
"""
from .transport_context import TransportContext
from .retry_hook import RetryHook, RetryDecision

__all__ = ["TransportContext", "RetryHook", "RetryDecision"]