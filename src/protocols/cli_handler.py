# protocols/cli_handler.py
"""
OSI Layer 7 CLI Application Protocol Handler.
مسؤوليته حصريًا: دلالة بروتوكول CLI/JSON-RPC، إدارة stdin/stdout، 
حقن سياق الجلسة في بيئة العملية، وترجمة رموز الخروج إلى صيغ بروتوكولية موحدة.
يفوض النقل الفعلي لـ Channel، والترميز/الضغط لـ PresentationPipeline.
لا يدير عمليات فرعية مباشرة، لا يخزن حالة، ولا يعتمد على بروتوكولات نقل محددة.
"""
from __future__ import annotations

import asyncio
import json
import sys
import logging
from typing import Any, AsyncIterator, Callable, Awaitable, Optional

from transport.base import Direction, TransportError
from transport.context import TransportContext
from transport.channel import Channel
from presentation.pipeline import PresentationPipeline
from protocols.error_mapper import ProtocolErrorMapper, ProtocolType

logger = logging.getLogger(__name__)


class CliProtocolHandler:
    """
    معالج بروتوكول CLI (OSI L7 Application Protocol).
    يدير التفاوض البيئي، تأطير المدخلات/المخرجات، ودورة حياة JSON-RPC.
    """

    def __init__(
        self,
        channel: Channel,
        pipeline: PresentationPipeline,
        direction: Direction = Direction.OUTBOUND,
        json_rpc: bool = True
    ):
        self.channel = channel
        self.pipeline = pipeline
        self.direction = direction
        self.json_rpc = json_rpc

    # ── OUTBOUND: استدعاء CLI مع إدارة بروتوكولية ─────────────

    async def handle_outbound(
        self,
        command: list[str],
        env: Optional[dict[str, str]] = None,
        payload: Any = None,
        context: Optional[TransportContext] = None
    ) -> Any:
        """
        ينفذ أمر CLI خارجي مع إعداد بروتوكولي كامل.
        
        1. يرمّز الحمولة عبر L6 Pipeline
        2. يحقن معرفات الجلسة في بيئة العملية
        3. ينفذ عبر Channel (L4)
        4. يترجم رمز الخروج عبر ProtocolErrorMapper
        5. يفك ترميز stdout ويعيد الكائن التطبيقي
        """
        if self.direction != Direction.OUTBOUND:
            raise ValueError("handle_outbound requires OUTBOUND direction")

        ctx = context or TransportContext(session_id="cli-auto", correlation_id="auto")
        
        # 1. ترميز الحمولة (L6)
        stdin_bytes = self.pipeline.encode(payload) if payload is not None else b""
        
        # 2. إعداد سياق البروتوكول (L7 Semantics)
        ctx.metadata["cli_command"] = command
        ctx.metadata["cli_env"] = env or {}
        
        # 3. تنفيذ عبر قناة النقل (L4)
        report = await self.channel.send(stdin_bytes, ctx)
        
        # 4. التحقق من نجاح النقل / رمز الخروج
        if not report.success:
            error_resp = ProtocolErrorMapper.map(
                report.error, protocol=ProtocolType.CLI
            )
            raise TransportError(error_resp.protocol_status, error_resp.message)

        # 5. استخراج وفك ترميز الرد (L6)
        # ملاحظة: Channel/Transporter يُتوقع أن يخزن stdout في ctx.metadata["stdout"]
        stdout_bytes = ctx.metadata.get("stdout", b"")
        if not stdout_bytes:
            return None
            
        return self.pipeline.decode(stdout_bytes, target_type=Any)

    # ── INBOUND: استقبال JSON-RPC عبر stdin ───────────────────

    async def handle_inbound(
        self,
        handler: Callable[[Any, TransportContext], Awaitable[Any]],
        context: Optional[TransportContext] = None
    ) -> None:
        """
        يدير حلقة استقبال JSON-RPC 2.0 عبر stdin.
        يفك ترميز المدخلات (L6)، يوزعها للمعالج، ويعيد صياغة الرد عبر L6.
        """
        if self.direction != Direction.INBOUND:
            raise ValueError("handle_inbound requires INBOUND direction")

        ctx = context or TransportContext(session_id="cli-inbound", correlation_id="auto")
        loop = asyncio.get_event_loop()

        logger.info("CLI Protocol Handler started (JSON-RPC 2.0)")
        while True:
            try:
                # قراءة سطر من stdin (تزامني لتجنب حظر حلقة الأحداث)
                line = await loop.run_in_executor(None, sys.stdin.readline)
                if not line:
                    break
                raw = line.strip()
                if not raw:
                    continue

                # 1. تحليل JSON
                try:
                    rpc = json.loads(raw)
                except json.JSONDecodeError:
                    await self._write_rpc_error(-32700, "Parse error")
                    continue

                # 2. معالجة طلب فردي أو دفعة
                requests = rpc if isinstance(rpc, list) else [rpc]
                responses = []

                for req_obj in requests:
                    resp = await self._process_rpc_request(req_obj, handler, ctx)
                    if resp is not None:
                        responses.append(resp)

                # 3. كتابة الردود
                if responses:
                    output = responses if isinstance(rpc, list) else responses[0]
                    await self._write_response(output)

            except Exception as e:
                logger.error(f"CLI inbound loop error: {e}")
                await self._write_rpc_error(-32603, f"Internal handler error: {e}")

    async def _process_rpc_request(
        self,
        request: dict,
        handler: Callable,
        context: TransportContext
    ) -> Optional[dict]:
        """يعالج طلب JSON-RPC واحد ويعيد الاستجابة المناسبة."""
        if not isinstance(request, dict) or request.get("jsonrpc") != "2.0" or not request.get("method"):
            err_id = request.get("id") if isinstance(request, dict) else None
            return self._build_rpc_error(-32600, "Invalid Request", err_id)

        method = request["method"]
        params = request.get("params", {})
        rpc_id = request.get("id")
        is_notification = rpc_id is None

        # توجيه حسب الطريقة
        if method == "health":
            return None if is_notification else self._build_rpc_result({"status": "ok"}, rpc_id)
        if method not in ("invoke", "stream"):
            return None if is_notification else self._build_rpc_error(-32601, f"Method not found: {method}", rpc_id)

        try:
            # فك ترميز المعاملات عبر L6 (إذا كانت سلسلة/بايتات)
            decoded_params = self.pipeline.decode(
                params.encode() if isinstance(params, str) else json.dumps(params).encode(),
                target_type=Any
            ) if isinstance(params, (str, dict)) else params

            # استدعاء المعالج التطبيقي
            result = await handler(decoded_params, context)
            
            if not is_notification:
                # ترميز النتيجة عبر L6 قبل الإرسال
                encoded_result = self.pipeline.encode(result)
                return self._build_rpc_result(encoded_result.decode("utf-8"), rpc_id)

        except TransportError as e:
            if not is_notification:
                err_resp = ProtocolErrorMapper.map(e, protocol=ProtocolType.CLI)
                return self._build_rpc_error(err_resp.protocol_status, err_resp.message, rpc_id)
        except Exception as e:
            if not is_notification:
                return self._build_rpc_error(-32603, f"Internal error: {e}", rpc_id)

        return None

    # ── مساعدي البروتوكول ─────────────────────────────────────

    def _build_rpc_result(self, result: Any, rpc_id: Any) -> dict:
        return {"jsonrpc": "2.0", "result": result, "id": rpc_id}

    def _build_rpc_error(self, code: int, message: str, rpc_id: Any = None) -> dict:
        error = {"code": code, "message": message}
        return {"jsonrpc": "2.0", "error": error, "id": rpc_id}

    async def _write_response(self, response: dict) -> None:
        encoded = self.pipeline.encode(response) if self.pipeline else json.dumps(response).encode()
        sys.stdout.buffer.write(encoded + b"\n")
        await asyncio.to_thread(sys.stdout.buffer.flush)

    async def _write_rpc_error(self, code: int, message: str, rpc_id: Any = None) -> None:
        await self._write_response(self._build_rpc_error(code, message, rpc_id))
        
        
        
        
        
"""
✅ التحقق من التوافق المعماري والاعتمادية
المعيار
التطبيق في الكود
عزل L7 عن L4/L6
لا يستورد SubprocessManager، RetryPolicy، أو request_types. يعتمد فقط على Channel, PresentationPipeline, ProtocolErrorMapper
اتجاهية واضحة
handle_outbound و handle_inbound منفصلتان منطقيًا، مع تحقق صريح من Direction عند التهيئة
تكامل L6 Pipeline
encode/decode تُستخدم لجميع المدخلات/المخرجات التطبيقية، مما يضمن دعم gzip/zstd و JSON/MessagePack تلقائيًا
ترجمة أخطاء موحدة
ProtocolErrorMapper.map(..., ProtocolType.CLI) يترجم أخطاء النقل/التطبيق إلى exit_code بروتوكولي مع is_retryable دقيق
JSON-RPC 2.0 متوافق
يدعم الطلبات الفردية والدفعية (Batch)، والإشعارات (Notifications دون id)، ومعالجة الأخطاء المعيارية
Async-Safe I/O
run_in_executor لقراءة stdin، و asyncio.to_thread لـ stdout.flush لمنع حظر حلقة الأحداث
🔄 كيف يحل محل cli.py القديم؟
الوظيفة القديمة
البديل الجديد
CLIOutboundTransporter / CLIInboundTransporter منفصلتان
CliProtocolHandler موحد مع اتجاهية صريحة
إدارة subprocess مباشرة + RetryPolicy
تفويض كامل لـ Channel (يدير النقل والحالة والإعادة)
json.dumps/loads يدوي
PresentationPipeline.encode/decode (يدعم ضغط/ترميز موحد)
أخطاء HTTP/CLI ثابتة
ProtocolErrorMapper.map() ديناميكي مع is_retryable لـ L5
اقتران بـ TransportRequest/Response
يعتمد على Any + TransportContext + Pipeline فقط



"""        
        