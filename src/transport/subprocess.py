# transport/subprocess.py
"""
OSI Layer 4 Subprocess Transporter (CLI IPC).
مسؤولية هذا الناقل حصريًا:
- تشغيل عمليات CLI معزولة وإدارة دورة حياتها (spawn/wait/cleanup)
- حقن سياق الجلسة (L5 Context) بشكل شفاف في متغيرات البيئة
- تسليم الحمولات (stdin) واستقبال المخرجات (stdout/stderr) مع تصنيف الأخطاء
- دعم إعادة المحاولة عبر RetryEngine المُحقون من L4/L5
لا يخزن حالة جلسة، لا يفسر محتوى البيانات، ويعتمد فقط على عقود الطبقة الرابعة.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import AsyncIterator, Optional

from transport.base import BaseTransporter, DeliveryReport, Direction, ErrorType, TransportError
from transport.context import TransportContext
from transport.retry import RetryEngine

logger = logging.getLogger(__name__)


class SubprocessTransporter(BaseTransporter):
    """
    ناقل النقل عبر العمليات الفرعية (OSI L4 Subprocess IPC).
    يُستخدم لنقل الرسائل إلى أدوات CLI أو مزودي نماذج يعملون كعمليات منفصلة.
    """

    def __init__(
        self,
        cmd: list[str],
        env_overrides: dict[str, str] | None = None,
        retry_engine: Optional[RetryEngine] = None,
        direction: Direction = Direction.OUTBOUND
    ):
        super().__init__(direction)
        self.cmd = cmd
        self.env_overrides = env_overrides or {}
        self.retry_engine = retry_engine
        self._proc: asyncio.subprocess.Process | None = None
        self._default_timeout = 120.0

    # ── L5 Context Injection (شفافية تامة) ──────────────────────

    def _build_env(self, context: TransportContext) -> dict[str, str]:
        """يُعد بيئة العملية مع حقن معرفات الجلسة بشكل شفاف."""
        env = os.environ.copy()
        env.update(self.env_overrides)
        
        # حقن سياق L5 كمتغيرات بيئة معتمة (لا يفسرها الناقل)
        env["SESSION_ID"] = context.session_id
        env["CORRELATION_ID"] = context.correlation_id
        env["STREAM_OFFSET"] = str(context.stream_offset)
        
        # إضافة وسوم إضافية من السياق (اختياري، حسب سياسات الأمان)
        for k, v in context.metadata.items():
            if k.startswith("CLI_"):  # بادئة آمنة لمنع التصادم
                env[k] = str(v)
                
        return env

    # ── Lifecycle Management ────────────────────────────────────

    async def _ensure_proc(self, context: TransportContext) -> asyncio.subprocess.Process:
        """يضمن وجود عملية نشطة، أو ينشئ واحدة جديدة ببيئة الجلسة الحالية."""
        if not self._proc or self._proc.returncode is not None:
            self._proc = await asyncio.create_subprocess_exec(
                *self.cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._build_env(context)
            )
            logger.debug(f"Subprocess spawned: pid={self._proc.pid}, cmd={' '.join(self.cmd)}")
        return self._proc

    async def _cleanup(self) -> None:
        """ينهي العملية بأمان ويحرر الموارد."""
        if self._proc and self._proc.returncode is None:
            try:
                self._proc.terminate()
                await asyncio.wait_for(self._proc.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                self._proc.kill()
                await self._proc.wait()
            logger.debug(f"Subprocess cleaned up: pid={self._proc.pid}")

    # ── Core I/O Operations (L4 Mechanism) ──────────────────────

    async def _do_send(self, payload: bytes, context: TransportContext) -> DeliveryReport:
        """المنطق الأساسي للإرسال الموحد. يُغلّف بـ RetryEngine عند التوفير."""
        proc = await self._ensure_proc(context)
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=payload),
                timeout=self._default_timeout
            )
            
            if proc.returncode != 0:
                err_msg = stderr.decode(errors="replace").strip()
                raise TransportError(
                    ErrorType.PERMANENT,
                    f"CLI exited with code {proc.returncode}: {err_msg}",
                    status_code=proc.returncode
                )
                
            return DeliveryReport(
                success=True,
                context=context,
                bytes_sent=len(payload),
                bytes_received=len(stdout),
                final_offset=context.stream_offset + len(stdout)
            )
            
        except asyncio.TimeoutError:
            await self._cleanup()
            raise TransportError(ErrorType.TRANSIENT, f"Subprocess timed out after {self._default_timeout}s")
        except Exception as e:
            await self._cleanup()
            if isinstance(e, TransportError):
                raise
            raise TransportError(ErrorType.TRANSIENT, str(e))

    async def _do_stream(self, payload: bytes, context: TransportContext) -> AsyncIterator[bytes]:
        """المنطق الأساسي للبث المتدفق. يُغلّف بـ RetryEngine عند التوفير."""
        proc = await self._ensure_proc(context)
        try:
            proc.stdin.write(payload)
            await proc.stdin.drain()
            proc.stdin.close()

            offset = context.stream_offset
            while True:
                line = await asyncio.wait_for(
                    proc.stdout.readline(),
                    timeout=self._default_timeout
                )
                if not line:
                    break
                yield line
                offset += len(line)

            await proc.wait()
            if proc.returncode != 0:
                stderr_data = await proc.stderr.read()
                raise TransportError(
                    ErrorType.PERMANENT,
                    f"Stream CLI exited with {proc.returncode}: {stderr_data.decode(errors='replace')}",
                    status_code=proc.returncode
                )
                
        except asyncio.TimeoutError:
            await self._cleanup()
            raise TransportError(ErrorType.TRANSIENT, f"Stream timed out after {self._default_timeout}s")
        except Exception as e:
            await self._cleanup()
            if isinstance(e, TransportError):
                raise
            raise TransportError(ErrorType.TRANSIENT, str(e))

    # ── Public Interface (L4 Contract) ──────────────────────────

    async def send(self, payload: bytes, context: TransportContext) -> DeliveryReport:
        """يرسل حمولة بايتات مع سياق جلسة شفاف، ويدعم إعادة المحاولة عبر L4 Engine."""
        if self.retry_engine:
            return await self.retry_engine.execute_with_retry(
                lambda: self._do_send(payload, context), context
            )
        return await self._do_send(payload, context)

    async def stream(
        self, payload: bytes, context: TransportContext
    ) -> AsyncIterator[bytes]:
        """يبث حمولة على شكل شرائح، مع دعم استئناف البث عبر RetryEngine."""
        if self.retry_engine:
            async for chunk in self.retry_engine.stream_with_retry(
                lambda: self._do_stream(payload, context), context
            ):
                yield chunk
        else:
            async for chunk in self._do_stream(payload, context):
                yield chunk

    async def close(self) -> None:
        await self._cleanup()
        self._proc = None

    async def __aenter__(self) -> SubprocessTransporter:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()