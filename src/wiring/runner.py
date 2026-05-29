# wiring/runner.py
"""
Application Runner & Graceful Shutdown Orchestrator.
يدير تجميع المركّب، تسجيل معالجات إشارات النظام (SIGINT/SIGTERM)،
ويضمن إطلاق الموارد عكسيًا وآمنًا عند الإنهاء أو الضغط على Ctrl+C.
"""
from __future__ import annotations

import asyncio
import logging
import signal
import sys
from typing import Optional

from wiring.assembler import CommunicationFabricAssembler, FabricClient

logger = logging.getLogger(__name__)


class AppRunner:
    """منقذ التطبيق: يربط التجميع، التشغيل، والإغلاق الآمن في دورة حياة واحدة."""

    def __init__(self, config_path: str = "transport_example.yaml"):
        self.config_path = config_path
        self.fabric_client: Optional[FabricClient] = None
        self._shutdown_event = asyncio.Event()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def start(self) -> None:
        """يجمع المركّب، يسجل الإشارات، ويانتظر حتى يتم طلب الإغلاق."""
        logger.info(f"🚀 Initializing AppRunner with config: {self.config_path}")
        
        # 1. تجميع المركّب
        assembler = CommunicationFabricAssembler(self.config_path)
        self.fabric_client = await assembler.assemble()
        
        # 2. بدء التشغيل
        await self.fabric_client.start()
        logger.info("✅ Communication Fabric started and ready")

        # 3. تسجيل معالجات الإشارات
        self._setup_signal_handlers()

        # 4. انتظار إشارة الإغلاق
        await self._shutdown_event.wait()
        logger.info("📥 Shutdown signal received. Initiating graceful teardown...")

    async def stop(self) -> None:
        """ينفّذ إغلاقًا منسقًا وعكسيًا للموارد."""
        if not self.fabric_client:
            return

        try:
            logger.info("🔌 Closing FabricClient and releasing resources...")
            await self.fabric_client.close()
            logger.info("✅ FabricClient closed successfully")
        except Exception as e:
            logger.error(f"❌ Error during fabric shutdown: {e}", exc_info=True)
        finally:
            self._shutdown_event.set()

    def _setup_signal_handlers(self) -> None:
        """يسجل معالجات إشارات OS المتوافقة مع async."""
        self._loop = asyncio.get_running_loop()

        def _on_signal():
            if not self._shutdown_event.is_set():
                logger.debug("OS signal intercepted")
                self._shutdown_event.set()

        # SIGINT (Ctrl+C) و SIGTERM (إيقاف خدمة/kill)
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                self._loop.add_signal_handler(sig, _on_signal)
            except NotImplementedError:
                # Windows لا يدعم add_signal_handler لـ SIGTERM، نستخدم fallback آمن
                signal.signal(sig, lambda s, f: _on_signal())
                logger.debug(f"⚠️ Signal {sig.name} registered via fallback (Windows compatible)")

    @classmethod
    async def run(cls, config_path: str = "transport_example.yaml") -> None:
        """نقطة دخول ثابتة تُسهّل التنفيذ من main.py أو CLI."""
        runner = cls(config_path)
        try:
            await runner.start()
        except asyncio.CancelledError:
            logger.info("🛑 Runner cancelled externally")
        finally:
            await runner.stop()