# wiring/pipelines/base.py
"""
Abstract Base for Directional Communication Pipelines.
يحدد العقد المشترك، إدارة السياق الموحد، وعزل الأخطاء الطبقي.
لا ينفذ منطق توجيه أو ترميز، بل يضمن سلوكيات مشتركة: تتبع، تنظيف، ومراقبة.
"""
from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Optional

from transport.context import TransportContext
from presentation.pipeline import PresentationPipeline
from session.session_dispatcher import SessionDispatcher

logger = logging.getLogger(__name__)


class PipelineExecutionError(Exception):
    """يُرفع عند فشل التنفيذ في أي طبقة من خطوط المعالجة الاتجاهية."""
    def __init__(self, layer: str, message: str, original: Optional[Exception] = None):
        self.layer = layer
        self.message = message
        self.original = original
        super().__init__(f"[{layer}] {message}")


class BaseCommunicationPipeline(ABC):
    """أساس الخطوط الاتجاهية. يدير السياق، العزل، والإحصائيات المشتركة."""

    def __init__(
        self,
        presentation: PresentationPipeline,
        dispatcher: SessionDispatcher,
        protocol_handler: Any,
        default_session_ttl: float = 3600.0
    ):
        self.presentation = presentation
        self.dispatcher = dispatcher
        self.protocol_handler = protocol_handler
        self.default_ttl = default_session_ttl
        self._stats = {"requests": 0, "errors": 0, "avg_latency_ms": 0.0}

    async def _build_context(
        self,
        session_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None
    ) -> TransportContext:
        """يُنشئ سياق جلسة موحد مع توليد معرفات افتراضية عند الحاجة."""
        sid = session_id or f"sess-{time.time_ns()}"
        cid = correlation_id or f"corr-{time.time_ns()}"
        return TransportContext(
            session_id=sid,
            correlation_id=cid,
            ttl=self.default_ttl,
            metadata=metadata or {}
        )

    async def _wrap_execution(self, layer: str, coro):
        """يغلّف التنفيذ بعزل أخطاء طبقي وإحصائيات دقيقة."""
        start = time.monotonic()
        try:
            self._stats["requests"] += 1
            result = await coro
            return result
        except PipelineExecutionError:
            self._stats["errors"] += 1
            raise
        except Exception as e:
            self._stats["errors"] += 1
            raise PipelineExecutionError(layer, str(e), original=e) from e
        finally:
            latency = (time.monotonic() - start) * 1000
            # تحديث متوسط زمني بسيط
            n = self._stats["requests"]
            self._stats["avg_latency_ms"] = (self._stats["avg_latency_ms"] * (n - 1) + latency) / n

    @abstractmethod
    async def execute(self, payload: Any, ctx: TransportContext) -> Any: ...