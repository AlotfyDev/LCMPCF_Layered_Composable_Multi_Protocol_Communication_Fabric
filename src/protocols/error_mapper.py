# protocols/error_mapper.py
"""
OSI Layer 7 Protocol Error Mapper.
مسؤوليته حصريًا: ترجمة الأخطاء الداخلية (L4/L5/L6/App) إلى صيغ بروتوكولية موحدة.
يغطي السيناريوهات الشبكية (HTTP, gRPC, WS) والمحلية (CLI, InProcess).
لا يدير إعادة المحاولة، لا يخزن حالة، ويعزل منطق التنسيق عن التنفيذ.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional
from dataclasses import dataclass, field

from transport.base import TransportError, ErrorType
from presentation.protocol import PresentationError


class ProtocolType(Enum):
    """بروتوكولات التطبيق المدعومة في الطبقة السابعة."""
    HTTP = "http"
    CLI = "cli"
    INPROCESS = "inprocess"
    GRPC = "grpc"
    WEBSOCKET = "websocket"
    LOCAL_IPC = "local_ipc"  # ← إضافة جديدة
    GRAPHQL = "graphql"  # ← إضافة جديدة
    WEBHOOK = "webhook"  # ← إضافة جديدة


@dataclass(frozen=True)
class ProtocolErrorResponse:
    """
    استجابة خطأ موحدة البروتوكول.
    protocol_status: يمثل HTTP status, CLI exit_code, gRPC status, أو WS close_code.
    is_retryable: تلميح لـ L5/L5 حول إمكانية الاستعادة (لا يفرض السياسة).
    """
    protocol_status: int
    message: str
    error_type: str
    details: Dict[str, Any] = field(default_factory=dict)
    headers: Dict[str, str] = field(default_factory=dict)
    is_retryable: bool = False


class ProtocolErrorMapper:
    """محوّل أخطاء بروتوكولي (OSI L7 Error Translation)."""

    # خرائط التحويل القياسية
    _HTTP_RETRYABLE = {429, 500, 502, 503, 504}
    _CLI_RETRYABLE = {1, 2}
    _GRPC_RETRYABLE = {4, 14}  # DEADLINE_EXCEEDED, UNAVAILABLE

    @classmethod
    def map(
        cls,
        error: Exception,
        protocol: ProtocolType = ProtocolType.HTTP,
        fallback_message: str = "Internal Error"
    ) -> ProtocolErrorResponse:
        """
        يترجم استثناء داخلي إلى استجابة خطأ بروتوكولية.
        
        Args:
            error: الاستثناء المرفوع من L4/L5/L6 أو التطبيق
            protocol: البروتوكول المستهدف للتنسيق
            fallback_message: رسالة افتراضية عند غياب التفاصيل
        """
        cat = cls._categorize(error, fallback_message)
        
        match protocol:
            case ProtocolType.HTTP: return cls._to_http(cat)
            case ProtocolType.CLI: return cls._to_cli(cat)
            case ProtocolType.INPROCESS: return cls._to_inprocess(cat)
            case ProtocolType.GRPC: return cls._to_grpc(cat)
            case ProtocolType.WEBSOCKET: return cls._to_websocket(cat)
            case _: return cls._to_http(cat)  # Fallback آمن

    @classmethod
    def _categorize(cls, error: Exception, fallback: str) -> Dict[str, Any]:
        """يصنف الخطأ الداخلي إلى خصائص قابلة للترجمة."""
        if isinstance(error, TransportError):
            return {
                "type": error.error_type.value,
                "message": error.message or str(error),
                "is_retryable": error.error_type == ErrorType.TRANSIENT,
                "original_status": error.status_code
            }
        if isinstance(error, PresentationError):
            return {
                "type": "presentation",
                "message": str(error),
                "is_retryable": False,  # أخطاء التسلسل/الضغط لا تُعاد عادةً
                "original_status": None
            }
        # استثناءات عامة
        return {
            "type": "unknown",
            "message": str(error) or fallback,
            "is_retryable": False,
            "original_status": None
        }

    @classmethod
    def _to_http(cls, cat: Dict[str, Any]) -> ProtocolErrorResponse:
        status = cat["original_status"] or 500
        if cat["type"] == "presentation": status = 400
        elif cat["type"] == "transient" and status == 500: status = 503
        
        return ProtocolErrorResponse(
            protocol_status=status,
            message=cat["message"],
            error_type=cat["type"],
            details={"protocol": "http"},
            headers={"Content-Type": "application/json"},
            is_retryable=cat["is_retryable"] and status in cls._HTTP_RETRYABLE
        )

    @classmethod
    def _to_cli(cls, cat: Dict[str, Any]) -> ProtocolErrorResponse:
        exit_code = 1
        if cat["is_retryable"]: exit_code = 2
        elif cat["type"] == "presentation": exit_code = 3  # خطأ تنسيق/إدخال

        return ProtocolErrorResponse(
            protocol_status=exit_code,
            message=cat["message"],
            error_type=cat["type"],
            details={"protocol": "cli"},
            is_retryable=cat["is_retryable"]
        )

    @classmethod
    def _to_inprocess(cls, cat: Dict[str, Any]) -> ProtocolErrorResponse:
        return ProtocolErrorResponse(
            protocol_status=1 if not cat["is_retryable"] else 2,
            message=cat["message"],
            error_type=cat["type"],
            details={"protocol": "inprocess"},
            is_retryable=cat["is_retryable"]
        )

    @classmethod
    def _to_grpc(cls, cat: Dict[str, Any]) -> ProtocolErrorResponse:
        status = 2  # UNKNOWN
        if cat["type"] == "presentation": status = 3  # INVALID_ARGUMENT
        elif cat["type"] == "transient": status = 14 # UNAVAILABLE
        elif cat["type"] == "permanent": status = 16 # UNAUTHENTICATED

        return ProtocolErrorResponse(
            protocol_status=status,
            message=cat["message"],
            error_type=cat["type"],
            details={"protocol": "grpc"},
            headers={"grpc-status": str(status)},
            is_retryable=cat["is_retryable"] and status in cls._GRPC_RETRYABLE
        )

    @classmethod
    def _to_websocket(cls, cat: Dict[str, Any]) -> ProtocolErrorResponse:
        close_code = 1011  # Internal Error
        if cat["type"] == "presentation": close_code = 1003  # Unsupported Data
        elif cat["is_retryable"]: close_code = 1001  # Going Away (Transient)

        return ProtocolErrorResponse(
            protocol_status=close_code,
            message=cat["message"],
            error_type=cat["type"],
            details={"protocol": "websocket"},
            is_retryable=cat["is_retryable"]
        )