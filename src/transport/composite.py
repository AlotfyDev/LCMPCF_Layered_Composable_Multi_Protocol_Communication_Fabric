# transport/composite.py
"""
OSI Layer 4 Composite Transporter (Multiplexing & Routing).
مسؤولية هذا الناقل حصريًا:
- توجيه شرائح النقل (Segments) عبر قنوات متعددة بناءً على استراتيجية محددة
- توفير آليات التحمل الأعطال (Fallback) والتوازي (Parallel) على مستوى النقل
- تجميع تقارير التسليم (DeliveryReport) من القنوات الفرعية بشكل متسق
- إدارة دورة حياة متعددة الناقلين (Composite Lifecycle)

Error Propagation Contract:
- FALLBACK: Raises only if ALL children fail; intermediate failures logged at DEBUG.
- PARALLEL: Raises if NO child succeeds; first success returns immediately.
- BROADCAST: Raises if ANY child fails with PERMANENT error (configurable via fail_fast).
- All raised errors are TransportError with appropriate ErrorType and exception chaining.

No session state storage, no payload interpretation, isolates routing logic from L7 protocols.
"""
from __future__ import annotations

import asyncio
import logging
import time
from enum import Enum
from typing import AsyncIterator, Callable, Awaitable, Optional, List, Tuple, Dict, Any

from transport.base import BaseTransporter, DeliveryReport, Direction, ErrorType, TransportError
from transport.context import TransportContext

logger = logging.getLogger(__name__)


class CompositeStrategy(Enum):
    """استراتيجيات توجيه الشرائح على مستوى النقل (OSI L4 Multiplexing)."""
    ROUTE = "route"          # توجيه حتمي لقناة واحدة بناءً على مفتاح
    FALLBACK = "fallback"    # محاولة تسلسلية حتى النجاح
    PARALLEL = "parallel"    # إرسال متوازي، إرجاع أول نجاح
    BROADCAST = "broadcast"  # إرسال متوازي، انتظار اكتمال جميع القنوات
    MUX = "mux"              # دمج مخرجات قنوات متعددة في دفق موحد


class CompositeTransporter(BaseTransporter):
    """
    ناقل النقل المركب (OSI L4 Composite IPC).
    يُستخدم لتوجيه الحمولة عبر قنوات متعددة (TCP, UDS, Subprocess, InProcess, WebSocket)
    مع الحفاظ على عقود النقل الموحدة وشفافية السياق.
    
    Designed for Channel wrapping: implements BaseTransporter contract fully,
    raises TransportError with proper ErrorType, and supports idempotent lifecycle.
    """

    def __init__(
        self,
        transporters: list[BaseTransporter],
        strategy: CompositeStrategy = CompositeStrategy.ROUTE,
        route_selector: Optional[Callable[[bytes, TransportContext], int]] = None,
        parallel_timeout: Optional[float] = None,
        broadcast_fail_fast: bool = True,
        enable_detailed_metrics: bool = False
    ):
        super().__init__(direction=Direction.OUTBOUND)
        if not transporters:
            raise TransporterConfigError("CompositeTransporter requires at least one child transporter")
        
        self._transporters = transporters
        self._strategy = strategy
        self._route_selector = route_selector or self._default_route_selector
        self._parallel_timeout = parallel_timeout
        self._broadcast_fail_fast = broadcast_fail_fast
        self._enable_detailed_metrics = enable_detailed_metrics
        self._server_tasks: list[asyncio.Task] = []
        
        # Optional: track child-level metrics if detailed observability is needed
        self._child_metrics: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def _default_route_selector(payload: bytes, context: TransportContext) -> int:
        """موجه افتراضي يعتمد على metadata أو التجزئة لتوزيع الحمل."""
        key = context.metadata.get("composite_route", 0)
        if isinstance(key, int):
            return key
        return hash(key) % 100 if isinstance(key, str) else 0

    # ── L4 Core Routing & Strategy Execution ──────────────────

    async def send(self, payload: bytes, context: TransportContext) -> DeliveryReport:
        """يرسل حمولة عبر القناة المناسبة حسب الاستراتيجية المحددة."""
        start_time = time.time()
        strategy = self._strategy.value
        
        try:
            if strategy == CompositeStrategy.ROUTE.value:
                idx = self._route_selector(payload, context)
                if not (0 <= idx < len(self._transporters)):
                    raise TransportError(
                        ErrorType.PERMANENT, 
                        f"Route index {idx} out of bounds [0, {len(self._transporters)})"
                    )
                logger.debug(f"Composite ROUTE: selecting transporter[{idx}]={self._transporters[idx].__class__.__name__}")
                return await self._transporters[idx].send(payload, context)

            elif strategy == CompositeStrategy.FALLBACK.value:
                return await self._execute_fallback_send(payload, context)

            elif strategy in (CompositeStrategy.PARALLEL.value, CompositeStrategy.BROADCAST.value):
                return await self._execute_parallel_send(payload, context)

            elif strategy == CompositeStrategy.MUX.value:
                return await self._execute_mux_send(payload, context)

            raise TransportError(ErrorType.PERMANENT, f"Unsupported composite strategy: {strategy}")
            
        except TransportError:
            # Re-raise TransportError as-is (already properly typed)
            raise
        except Exception as e:
            # Wrap unexpected errors with proper chaining
            logger.error(f"Composite send failed unexpectedly: {e}", exc_info=True)
            raise TransportError(ErrorType.TRANSIENT, f"Composite send error: {e}") from e
        finally:
            elapsed = time.time() - start_time
            logger.debug(
                f"Composite send completed: strategy={strategy}, elapsed={elapsed:.3f}s, "
                f"transporters={len(self._transporters)}"
            )

    async def _execute_fallback_send(self, payload: bytes, context: TransportContext) -> DeliveryReport:
        """تنفيذ استراتيجية FALLBACK: محاولة تسلسلية حتى النجاح."""
        last_err: Optional[Exception] = None
        for idx, tp in enumerate(self._transporters):
            tp_name = tp.__class__.__name__
            try:
                logger.debug(f"Fallback attempt [{idx+1}/{len(self._transporters)}]: {tp_name}")
                report = await tp.send(payload, context)
                if report.success:
                    logger.info(f"Fallback succeeded on transporter[{idx}]={tp_name}")
                    return report
                last_err = report.error or RuntimeError(f"{tp_name} reported failure without exception")
                logger.debug(f"Fallback transporter[{idx}]={tp_name} returned unsuccessful report: {report.error}")
            except Exception as e:
                last_err = e
                logger.debug(f"Fallback transporter[{idx}]={tp_name} failed: {e}", exc_info=False)
                continue
        
        logger.warning(f"All {len(self._transporters)} fallback transporters failed")
        raise TransportError(
            ErrorType.PERMANENT, 
            f"All composite fallback transporters failed (last: {last_err})"
        ) from last_err

    async def _execute_parallel_send(self, payload: bytes, context: TransportContext) -> DeliveryReport:
        """تنفيذ استراتيجيات PARALLEL/BROADCAST مع دعم timeout اختياري."""
        tasks = [tp.send(payload, context) for tp in self._transporters]
        wait_all = (self._strategy == CompositeStrategy.BROADCAST)
        
        try:
            if self._parallel_timeout:
                results = await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True), 
                    timeout=self._parallel_timeout
                )
            else:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
            return self._aggregate_parallel_results(results, wait_all=wait_all)
            
        except asyncio.TimeoutError as e:
            logger.warning(f"Parallel send timed out after {self._parallel_timeout}s")
            # Cancel pending tasks to avoid resource leaks
            for task in tasks:
                if not task.done():
                    task.cancel()
            raise TransportError(
                ErrorType.TRANSIENT, 
                f"Parallel send timeout after {self._parallel_timeout}s"
            ) from e
        except Exception as e:
            logger.error(f"Parallel send failed: {e}", exc_info=True)
            raise TransportError(ErrorType.TRANSIENT, f"Parallel send error: {e}") from e

    async def _execute_mux_send(self, payload: bytes, context: TransportContext) -> DeliveryReport:
        """MUX للإرسال المتزامن يجمع تقارير التسليم ويعيد موحدًا."""
        # Currently equivalent to PARALLEL; can be extended for ordered merging
        return await self._execute_parallel_send(payload, context)

    def _aggregate_parallel_results(
        self, 
        results: list, 
        wait_all: bool = False
    ) -> DeliveryReport:
        """تجميع نتائج العمليات المتوازية مع تحكم في سياسة الأخطاء."""
        successes: List[DeliveryReport] = []
        errors: List[Exception] = []
        total_sent = 0
        total_recv = 0
        first_context: Optional[TransportContext] = None
        
        for idx, r in enumerate(results):
            tp_name = self._transporters[idx].__class__.__name__ if idx < len(self._transporters) else "unknown"
            
            if isinstance(r, DeliveryReport):
                if r.success:
                    successes.append(r)
                    total_sent += r.bytes_sent
                    total_recv += r.bytes_received
                    if first_context is None:
                        first_context = r.context
                    if self._enable_detailed_metrics:
                        self._child_metrics[tp_name] = {"status": "success", "report": r}
                else:
                    errors.append(r.error or RuntimeError(f"{tp_name} reported failure"))
                    if self._enable_detailed_metrics:
                        self._child_metrics[tp_name] = {"status": "unsuccessful", "error": r.error}
            elif isinstance(r, Exception):
                errors.append(r)
                if self._enable_detailed_metrics:
                    self._child_metrics[tp_name] = {"status": "exception", "error": str(r)}
            else:
                errors.append(RuntimeError(f"Unexpected result type: {type(r)}"))

        # سياسة BROADCAST: فشل سريع إذا طُلب
        if wait_all and self._broadcast_fail_fast and errors:
            first_error = next((e for e in errors if isinstance(e, TransportError) and e.error_type == ErrorType.PERMANENT), errors[0])
            logger.warning(f"BROADCAST failed fast: {len(errors)}/{len(results)} transporters failed")
            raise TransportError(
                ErrorType.PERMANENT if isinstance(first_error, TransportError) and first_error.error_type == ErrorType.PERMANENT else ErrorType.TRANSIENT,
                f"Broadcast failed: {len(errors)}/{len(results)} transporters failed"
            ) from first_error

        if not successes:
            logger.error(f"All {len(results)} parallel transporters failed")
            first_error = errors[0] if errors else RuntimeError("No errors captured")
            raise TransportError(ErrorType.PERMANENT, "All parallel transporters failed") from first_error

        # بناء تقرير مجمع
        successful_reports = [r for r in results if isinstance(r, DeliveryReport) and r.success]
        return DeliveryReport(
            success=True,
            context=first_context or successful_reports[0].context if successful_reports else None,
            bytes_sent=total_sent,
            bytes_received=total_recv,
            final_offset=max((s.final_offset for s in successful_reports), default=0),
            retry_count=max((s.retry_count for s in successful_reports), default=0),
            # Optional: embed child details if detailed metrics enabled
            metadata={"composite": {
                "strategy": self._strategy.value,
                "successful_children": len(successes),
                "failed_children": len(errors),
                "total_children": len(results)
            }} if self._enable_detailed_metrics else None
        )

    async def stream(
        self, payload: bytes, context: TransportContext
    ) -> AsyncIterator[bytes]:
        """يبث حمولة عبر القناة المناسبة مع دعم الاستئناف المتعدد."""
        strategy = self._strategy.value
        
        if strategy == CompositeStrategy.ROUTE.value:
            idx = self._route_selector(payload, context)
            if not (0 <= idx < len(self._transporters)):
                raise TransportError(ErrorType.PERMANENT, f"Route index {idx} out of bounds")
            async for chunk in self._transporters[idx].stream(payload, context):
                yield chunk

        elif strategy == CompositeStrategy.FALLBACK.value:
            async for chunk in self._execute_fallback_stream(payload, context):
                yield chunk

        elif strategy in (CompositeStrategy.PARALLEL.value, CompositeStrategy.BROADCAST.value, CompositeStrategy.MUX.value):
            async for chunk in self._merge_parallel_streams(payload, context):
                yield chunk
        else:
            raise TransportError(ErrorType.PERMANENT, f"Strategy {strategy} not supported for stream")

    async def _execute_fallback_stream(self, payload: bytes, context: TransportContext) -> AsyncIterator[bytes]:
        """تنفيذ STREAM لاستراتيجية FALLBACK."""
        last_err = None
        for idx, tp in enumerate(self._transporters):
            tp_name = tp.__class__.__name__
            try:
                logger.debug(f"Fallback stream attempt [{idx+1}/{len(self._transporters)}]: {tp_name}")
                async for chunk in tp.stream(payload, context):
                    yield chunk
                logger.info(f"Fallback stream succeeded on transporter[{idx}]={tp_name}")
                return
            except Exception as e:
                last_err = e
                logger.debug(f"Fallback stream transporter[{idx}]={tp_name} failed: {e}", exc_info=False)
                continue
        
        logger.warning(f"All {len(self._transporters)} fallback stream transporters failed")
        raise TransportError(ErrorType.PERMANENT, "All composite fallback streams failed") from last_err

    async def _merge_parallel_streams(self, payload: bytes, context: TransportContext) -> AsyncIterator[bytes]:
        """دمج متزامن لشرائح متعددة مع الحفاظ على حدود الشرائح ومعالجة الأخطاء بمرونة."""
        queues: list[asyncio.Queue] = [asyncio.Queue() for _ in self._transporters]
        tasks = []
        active = len(queues)

        async def _reader(tp: BaseTransporter, q: asyncio.Queue, tp_name: str):
            try:
                async for chunk in tp.stream(payload, context):
                    await q.put(("data", chunk))
                await q.put(("done", None))
            except Exception as e:
                logger.warning(f"Stream reader failed for {tp_name}: {e}")
                await q.put(("error", e))

        for tp, q in zip(self._transporters, queues):
            tp_name = tp.__class__.__name__
            task = asyncio.create_task(_reader(tp, q, tp_name))
            tasks.append(task)

        errors: List[Exception] = []
        while active > 0:
            for q in list(queues):  # Copy to allow modification during iteration
                try:
                    msg_type, data = q.get_nowait()
                except asyncio.QueueEmpty:
                    continue
                
                if msg_type == "data":
                    yield data
                elif msg_type == "done":
                    active -= 1
                    queues.remove(q)
                    logger.debug(f"Stream reader completed, remaining={active}")
                elif msg_type == "error":
                    errors.append(data)
                    active -= 1
                    queues.remove(q)
                    logger.warning(f"Stream reader failed, remaining={active}")
                    if self._strategy == CompositeStrategy.BROADCAST and self._broadcast_fail_fast:
                        # Cancel remaining tasks for fast failure
                        for t in tasks:
                            if not t.done():
                                t.cancel()
                        raise TransportError(ErrorType.PERMANENT, "Parallel stream failed (fail_fast)") from data
            
            if active > 0:
                await asyncio.sleep(0.01)  # Prevent CPU spin

        # Cleanup: ensure all tasks are done
        for t in tasks:
            if not t.done():
                t.cancel()
                try:
                    await t
                except asyncio.CancelledError:
                    pass

        # Final error handling based on strategy
        if errors and self._strategy == CompositeStrategy.BROADCAST:
            raise TransportError(ErrorType.TRANSIENT, f"Parallel stream completed with {len(errors)} errors") from errors[0]

    # ── Inbound & Lifecycle ───────────────────────────────────

    async def serve(self, handler: Callable[[bytes, TransportContext], Awaitable[bytes]]) -> None:
        """يُشغل جميع الناقلين الواردين بشكل متزامن."""
        if self.direction != Direction.INBOUND:
            raise TransportError(ErrorType.PERMANENT, "serve() requires INBOUND direction")
            
        inbound_tps = [tp for tp in self._transporters if tp.direction == Direction.INBOUND]
        if not inbound_tps:
            raise TransportError(ErrorType.PERMANENT, "No inbound transporters in composite")
        
        logger.info(f"Composite inbound starting: {len(inbound_tps)}/{len(self._transporters)} listeners")
        
        # تشغيل جميع الخوادم كمهام خلفية لمنع الحجب
        self._server_tasks = [
            asyncio.create_task(self._serve_single(tp, handler)) for tp in inbound_tps
        ]
        
        # Wait for all servers (they run forever unless cancelled)
        await asyncio.gather(*self._server_tasks, return_exceptions=True)

    async def _serve_single(self, transporter: BaseTransporter, handler: Callable) -> None:
        """غلاف آمن لتشغيل ناقل واحد مع معالجة الأخطاء الفردية."""
        tp_name = transporter.__class__.__name__
        try:
            await transporter.serve(handler)
        except asyncio.CancelledError:
            logger.debug(f"Composite: cancelled inbound for {tp_name}")
            raise
        except Exception as e:
            logger.error(f"Composite: inbound failed for {tp_name}: {e}", exc_info=True)
            # Don't propagate: let other transporters continue serving

    async def close(self) -> None:
        """يُغلق جميع الناقلين الفرعيين والمهام الخلفية بشكل آمن ومتكرر (Idempotent)."""
        logger.debug(f"Composite closing: {len(self._transporters)} transporters, {len(self._server_tasks)} server tasks")
        
        # Cancel and await server tasks
        for task in self._server_tasks:
            if not task.done():
                task.cancel()
        if self._server_tasks:
            results = await asyncio.gather(*self._server_tasks, return_exceptions=True)
            for i, res in enumerate(results):
                if isinstance(res, Exception) and not isinstance(res, asyncio.CancelledError):
                    logger.warning(f"Server task[{i}] closed with error: {res}")
        self._server_tasks.clear()
        
        # Close all child transporters with error tolerance
        close_errors: List[Tuple[str, Exception]] = []
        for idx, tp in enumerate(self._transporters):
            tp_name = tp.__class__.__name__
            try:
                await tp.close()
                logger.debug(f"Closed transporter[{idx}]={tp_name}")
            except Exception as e:
                close_errors.append((tp_name, e))
                logger.warning(f"Failed to close transporter[{idx}]={tp_name}: {e}")
        
        if close_errors:
            logger.warning(f"Composite close completed with {len(close_errors)} transporter errors")
        
        # Clear metrics if enabled
        if self._enable_detailed_metrics:
            self._child_metrics.clear()
            
        logger.debug("Composite transporter resources released")

    async def __aenter__(self) -> CompositeTransporter:
        # Composite doesn't have its own "open", but children may need initialization
        # This is handled by Channel.open() -> _ensure_connection() if needed
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()


class TransporterConfigError(ValueError):
    """خطأ تكوين في الناقل المركب."""
    pass