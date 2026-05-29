# wiring/assembler.py
"""
Fabric Composition Root (Assembler + FabricClient).
مسؤوليته حصريًا:
1. قراءة التكوين (YAML/ENV)
2. تجميع المكونات الطبقية عبر مصانع/مزودين معزولين
3. تسجيلها في LayerRegistry و PipelineRegistry
4. بناء الخطوط الاتجاهية (Inbound/Outbound)
5. إرجاع FabricClient جاهز للاستخدام الإنتاجي

✅ لا يحتوي على منطق أعمال، لا يدير مقابس، لا يعرف بروتوكولات محددة.
✅ يعتمد كليًا على العقود، التكوين، والسجلات التي بنيناها.
✅ يدعم الإغلاق الآمن، الفحص الصحي، والتبديل الديناميكي.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, AsyncIterator, Dict, Optional

from wiring.config.loader import load_config  # يُفترض وجوده من الخطوة السابقة
from wiring.registry.layer_registry import LayerRegistry, RegistryError
from wiring.registry.pipeline_registry import PipelineRegistry, PipelineMetadata
from wiring.pipelines.inbound import InboundCommunicationPipeline
from wiring.pipelines.outbound import OutboundCommunicationPipeline, PipelineExecutionError
from wiring.pipelines.base import BaseCommunicationPipeline

# عقود ومكونات أساسية (يتم استيرادها من الطبقات المقابلة)
from transport.context import TransportContext
from session.session_dispatcher import SessionDispatcher
from session.session_registry import SessionRegistry
from network.protocol import IChannelPool, ISessionRouter
from presentation.pipeline import PresentationPipeline
from protocols.protocol import IProtocolHandler
from wiring.contracts.communication_gateway import ICommunicationGateway
from wiring.factories.network_provider import build_channel_pool, build_load_balancer, build_session_router
from wiring.factories.transport_provider import build_channel, build_transport_config_from_protocol
from wiring.factories.session_provider import build_session_registry as _build_session_registry, build_session_dispatcher as _build_session_dispatcher
from wiring.factories.presentation_provider import build_presentation_pipeline as _build_presentation_pipeline
from wiring.factories.protocol_provider import build_all_protocol_handlers
from transport.base import Direction
from transport.channel.protocol import IChannel
from transport.config import TransportConfig

logger = logging.getLogger(__name__)


class FabricClient:
    """
    الواجهة الموحدة لمركّب الاتصالات (Multi-Protocol Communication Fabric Facade).
    يدير التوجيه، دورة الحياة، والفحص الصحي، ويعزل المستهلك عن تعقيد الطبقات الداخلية.
    """

    def __init__(
        self,
        layer_registry: LayerRegistry,
        pipeline_registry: PipelineRegistry,
        config: Any
    ):
        self._layer_registry = layer_registry
        self._pipeline_registry = pipeline_registry
        self.config = config
        self._started = False

    # ── Unified High-Level API ───────────────────────────────

    async def send(
        self,
        payload: Any,
        protocol: str = "http",
        session_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        stream: bool = False,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Any:
        """يرسل حمولة تطبيقية عبر البروتوكول والاتجاه الافتراضي (Outbound)."""
        pipeline = await self._resolve_pipeline("outbound", protocol)
        if stream:
            return await pipeline.send(payload, session_id, correlation_id, stream=True, metadata=metadata)
        return await pipeline.send(payload, session_id, correlation_id, metadata=metadata)

    async def receive(
        self,
        raw_bytes: bytes,
        protocol: str = "http",
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
        channel_ref: Optional[str] = None
    ) -> Any:
        """يستقبل بيانات شبكية خام ويعيد كائنًا تطبيقيًا جاهزًا (Inbound)."""
        pipeline = await self._resolve_pipeline("inbound", protocol)
        return await pipeline.receive(raw_bytes, session_id, metadata, channel_ref)

    async def receive_stream(
        self,
        byte_stream: AsyncIterator[bytes],
        protocol: str = "http",
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None
    ) -> AsyncIterator[Any]:
        """يستقبل تدفقًا شبكيًا مستمرًا ويعيد تدفق كائنات تطبيقية."""
        pipeline = await self._resolve_pipeline("inbound", protocol)
        return await pipeline.receive_stream(byte_stream, session_id, metadata)

    async def close_session(self, session_id: str, protocol: str = "http") -> None:
        """يُنهي جلسة صراحةً ويحرر مواردها عبر الخط المناسب."""
        pipeline = await self._resolve_pipeline("inbound", protocol)
        await pipeline.finalize(session_id, reason="client_request")

    # ── Dynamic Resolution & Routing ─────────────────────────

    async def get_pipeline(self, direction: str, protocol: str) -> BaseCommunicationPipeline:
        """يعيد خط المعالجة المطلوب مباشرةً للتخصيص المتقدم."""
        return await self._resolve_pipeline(direction, protocol)

    async def list_pipelines(self) -> list[PipelineMetadata]:
        """يعيد قائمة الخطوط النشطة للمراقبة والتصحيح."""
        return await self._pipeline_registry.list_all()

    # ── Lifecycle & Health ───────────────────────────────────

    async def start(self) -> None:
        """يبدأ المكونات الأساسية ويؤكّد جاهزية المركّب."""
        if self._started:
            return
        # تشغيل صيانة الجلسات والفحوصات الصحية للمجمع
        session_reg = await self._layer_registry.get_session_registry()
        if hasattr(session_reg, "start_maintenance"):
            await session_reg.start_maintenance()
        
        self._started = True
        logger.info("CommunicationFabricClient started and ready")

    async def close(self) -> None:
        """يُغلق المركّب وينظّف الموارد عكسيًا حسب ترتيب الاعتمادية."""
        if not self._started:
            return
        logger.info("Shutting down CommunicationFabricClient...")
        await self._pipeline_registry.close()
        await self._layer_registry.close()
        self._started = False
        logger.info("CommunicationFabricClient fully closed")

    async def health_check(self) -> Dict[str, Any]:
        """فحص حيوي سريع لحالة المركّب والخطوط المسجلة."""
        pipe_stats = await self._pipeline_registry.get_stats()
        return {
            "status": "healthy" if self._started else "stopped",
            "started": self._started,
            "active_pipelines": pipe_stats["total_pipelines"],
            "pipelines": pipe_stats["pipelines"],
            "timestamp": time.time()
        }

    # ── Internal Helpers ─────────────────────────────────────

    async def _resolve_pipeline(self, direction: str, protocol: str) -> BaseCommunicationPipeline:
        pipeline = await self._pipeline_registry.get(direction, protocol)
        if pipeline is None:
            raise PipelineExecutionError(
                "Routing", 
                f"No pipeline registered for direction='{direction}', protocol='{protocol}'"
            )
        return pipeline


class CommunicationFabricAssembler:
    """
    جذر التجميع (Composition Root).
    يقرأ التكوين، يبني المكونات، يسجلها، ويربطها في FabricClient جاهز.
    """

    def __init__(self, config_path: str = "transport_example.yaml"):
        self.config_path = config_path
        self.layer_registry = LayerRegistry()
        self.pipeline_registry = PipelineRegistry()
        self._started = False
        self.client: Optional[FabricClient] = None

    async def assemble(self) -> FabricClient:
        """يُنفذ عملية التجميع الكاملة ويعيد عميلًا جاهزًا."""
        logger.info(f"Assembling Communication Fabric from {self.config_path}...")
        
        # 1. تحميل التكوين
        cfg = load_config(self.config_path)
        logger.debug("Configuration loaded successfully")

        # 2. تجميع المكونات الطبقية (يتم تفويضها لمزودين/مصانع في الإنتاج)
        # هنا مثال مبسط يوضح نمط الربط، يمكن استبداله بـ Provider classes لاحقًا
        pool = self._build_network_pool(cfg.network)
        strategy = build_load_balancer(cfg.network.load_balancer_strategy)
        router = build_session_router(strategy)
        registry = self._build_session_registry(cfg.session)
        dispatcher = self._build_session_dispatcher(cfg.session, pool, registry, router)
        pipeline = self._build_presentation_pipeline(cfg.presentation)
        handlers = self._build_protocol_handlers(cfg.protocols, pipeline)

        # 3. تسجيل في السجل الطبقي
        await self.layer_registry.register("network", "channel_pool", pool)
        await self.layer_registry.register("session", "dispatcher", dispatcher)
        await self.layer_registry.register("session", "registry", registry)
        await self.layer_registry.register("presentation", "pipeline", pipeline)
        for proto, handler in handlers.items():
            await self.layer_registry.register("protocol", proto, handler)

        # 4. تجميع الخطوط الاتجاهية
        for proto, handler in handlers.items():
            out_pipe = OutboundCommunicationPipeline(pipeline, dispatcher, handler, cfg.session.default_ttl)
            in_pipe = InboundCommunicationPipeline(pipeline, dispatcher, handler, cfg.session.default_ttl)
            await self.pipeline_registry.register("outbound", proto, out_pipe)
            await self.pipeline_registry.register("inbound", proto, in_pipe)

        # 5. إنشاء العميل وإرجاعه
        self.client = FabricClient(self.layer_registry, self.pipeline_registry, cfg)
        logger.info("Fabric assembled successfully. Client ready.")
        return self.client

    # ── Builders (Backed by Factory Providers) ───────────

    def _build_network_pool(self, cfg: Any) -> IChannelPool:
        tcfg = TransportConfig(
            transport_type="inprocess",
            direction="outbound",
        )
        return build_channel_pool(
            config=tcfg,
            max_size=getattr(cfg, "pool_max_size", 50),
            idle_timeout=getattr(cfg, "pool_idle_timeout", 120.0),
        )

    def _build_session_dispatcher(self, cfg: Any, pool: IChannelPool, registry: SessionRegistry, router: ISessionRouter) -> SessionDispatcher:
        return _build_session_dispatcher(
            registry=registry,
            pool=pool,
            router=router,
            max_failover_attempts=getattr(cfg, "max_failover_attempts", 3),
            failover_delay=getattr(cfg, "failover_delay", 1.0),
        )

    def _build_session_registry(self, cfg: Any) -> SessionRegistry:
        return _build_session_registry(
            default_ttl=getattr(cfg, "default_ttl", 3600.0),
            idle_timeout=getattr(cfg, "idle_timeout", 300.0),
            eviction_interval=getattr(cfg, "eviction_interval", 60.0),
        )

    def _build_presentation_pipeline(self, cfg: Any) -> PresentationPipeline:
        return _build_presentation_pipeline(
            direction=Direction.OUTBOUND,
            serializer_name=getattr(cfg, "serializer", "json"),
            compressor_name=getattr(cfg, "compressor", "gzip"),
            min_compression_bytes=getattr(cfg, "min_compression_bytes", 1024),
            auto_detect=getattr(cfg, "auto_detect_compression", True),
            bypass_inprocess=getattr(cfg, "bypass_inprocess", True),
        )

    def _build_protocol_handlers(self, cfg: Any, pipeline: PresentationPipeline) -> Dict[str, IProtocolHandler]:
        channels: Dict[str, IChannel] = {}
        for name, entry_info in cfg.items() if isinstance(cfg, dict) else []:
            tcfg = build_transport_config_from_protocol(
                protocol_name=name,
                transport_type=getattr(entry_info, "transport", "inprocess"),
                direction=getattr(entry_info, "direction", "outbound"),
                endpoint=getattr(entry_info, "endpoint", None),
                port=getattr(entry_info, "port", None),
                socket_path=getattr(entry_info, "socket_path", None),
            )
            try:
                channels[name] = build_channel(tcfg)
            except Exception as e:
                logger.warning(f"Failed to build channel for '{name}': {e}")

        inbound_pipeline = _build_presentation_pipeline(
            direction=Direction.INBOUND,
            serializer_name="json",
            compressor_name="gzip",
        )
        return build_all_protocol_handlers(
            protocol_configs=cfg if isinstance(cfg, dict) else {},
            channels=channels,
            outbound_pipeline=pipeline,
            inbound_pipeline=inbound_pipeline,
        )
        
  
    async def liveness_check(self) -> Dict[str, Any]:
        """هل العملية/الحلقة غير المتزامنة تعمل؟ (K8s Liveness)"""
        import time
        return {
            "status": "alive",
            "started": self._started,
            "loop_running": asyncio.get_event_loop().is_running(),
            "timestamp": time.time()
        }

    async def readiness_check(self) -> Dict[str, Any]:
        """هل النظام جاهز لاستقبال حركة المرور؟ (K8s Readiness)"""
        import time
        pipe_stats = await self._pipeline_registry.get_stats()
        layer_stats = await self._layer_registry.list_registered()
        
        is_ready = (
            self._started and 
            pipe_stats["total_pipelines"] > 0 and 
            len(layer_stats) >= 4  # network, session, presentation, protocol على الأقل
        )
        
        return {
            "status": "ready" if is_ready else "not_ready",
            "pipelines_active": pipe_stats["total_pipelines"],
            "components_registered": len(layer_stats),
            "timestamp": time.time()
        }

    
    # --- End of functional code ---