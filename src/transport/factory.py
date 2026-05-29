# transport/factory.py
"""
OSI Layer 4 Transport Factory & Orchestrator.
مسؤولية هذا المصنع حصريًا:
- قراءة TransportConfig التصريحية
- تهيئة RetryEngine مع حقن RetryHook من L5 (صريح أو تصريحي)
- اختيار الناقل الملموس (CLI, InProcess, TCP, UDS, WebSocket, Composite)
- توفير خيار تغليف الناقل بـ Channel لإدارة الحالة والمقاييس (Orchestration Layer)
- تجميع القطع في كومة نقل (Transport Stack) متسقة وقابلة للاختبار

Design Principles:
- Backward Compatible: create() returns BaseTransporter by default
- Channel-Ready: create_channel() returns IChannel with state/metrics orchestration
- Extensible: Register custom builders without modifying core logic
- DIP Compliant: Depends on abstractions (BaseTransporter, IChannel), not concretions
- Fail-Fast on Config Errors, Graceful on Optional Dependencies
"""
from __future__ import annotations

import logging
from typing import Optional, Callable, Dict, List, Any, Union, TypeVar, overload, cast

from transport.config import TransportConfig, TransportType, ChannelSettingsConfig
from transport.context import RetryHook, TransportContext
from transport.retry import RetryEngine
from transport.base import BaseTransporter, Direction, TransportError, DeliveryReport

logger = logging.getLogger(__name__)

# Type alias for flexibility: can return either raw transporter or wrapped channel
TTransport = TypeVar('TTransport', bound=BaseTransporter)


class TransportFactoryError(Exception):
    """خطأ تكوين أو تركيب في مصنع النقل (يُرفع لأخطاء التكوين الحرجة)."""
    pass


class TransportFactory:
    """
    مصنع تركيب الطبقة الرابعة (L4 Transport Stack Builder).
    يربط التكوين التصريحي بالمحولات الملموسة مع سياسة استعادة L5.
    
    Features:
    - Supports all transport types: CLI, InProcess, TCP, UDS, WebSocket, Composite
    - Optional Channel wrapping for state management & observability
    - Lazy builder registration to prevent circular imports
    - Priority-based RetryHook resolution (explicit > declarative > default)
    - Unified error policy: Fail-fast on config errors, graceful on optional deps
    """

    # سجل ديناميكي للبناء لتجنب الاستيرادات الدائرية وتمكين التوسع
    # Format: {TransportType: {direction_str: builder_callable}}
    _builders: Dict[TransportType, Dict[str, Callable]] = {}

    @classmethod
    def register(cls, transport_type: TransportType, direction: str, builder: Callable) -> None:
        """
        تسجيل دالة بناء مخصصة لناقل معين.
        
        Args:
            transport_type: نوع الناقل (من Enum TransportType)
            direction: "inbound" أو "outbound"
            builder: دالة تأخذ (config: TransportConfig, retry_engine: RetryEngine) وتعيد BaseTransporter
        """
        cls._builders.setdefault(transport_type, {})[direction] = builder
        logger.debug(f"Registered builder for {transport_type.value}/{direction}")

    @classmethod
    def _resolve_retry_hook(
        cls,
        config: TransportConfig,
        custom_hook: Optional[RetryHook] = None
    ) -> Optional[RetryHook]:
        """
        يحل سياسة إعادة المحاولة من الأولويات:
        1. خطاف صريح من الكود (custom_hook) ← أعلى أولوية
        2. خطاف تصريحي من التكوين (hook_type + hook_kwargs)
        3. None ← سلوك L4 الافتراضي
        
        سياسة الأخطاء:
        - أخطاء التكوين (ValueError في المعاملات) → رفع استثناء فوري
        - أخطاء الاعتماديات الاختيارية (ImportError) → تسجيل تحذير والمتابعة بسلوك افتراضي
        """
        # أولوية 1: خطاف صريح مُحقن من الكود
        if custom_hook is not None:
            return custom_hook

        # أولوية 2: خطاف تصريحي من التكوين
        if config.retry_policy.hook_type:
            try:
                # استيراد متأخر لتجنب الدوائر ولتمكين الاختبار المعزول
                from session.hooks.retry_hooks import create_retry_hook
                return create_retry_hook(
                    config.retry_policy.hook_type,
                    **(config.retry_policy.hook_kwargs or {})
                )
            except ImportError as e:
                # اعتمادية اختيارية: نستمر بدون Hook بأمان
                logger.debug(
                    f"RetryHook module not available: {e}. "
                    f"Proceeding with default retry behavior for {config.transport_type.value}"
                )
                return None
            except ValueError as e:
                # خطأ في التكوين: نرفعه كـ FactoryError ليراه المستهلك فورًا
                raise TransportFactoryError(
                    f"Invalid RetryHook configuration: {e}"
                ) from e

        # أولوية 3: لا خطاف (سلوك L4 الافتراضي)
        return None

    @classmethod
    @overload
    def create(
        cls,
        config: TransportConfig,
        retry_hook: Optional[RetryHook] = None,
        error_classifier: Optional[Callable[[Exception], TransportError]] = None,
        wrap_with_channel: bool = False
    ) -> BaseTransporter: ...

    @classmethod
    @overload
    def create(
        cls,
        config: TransportConfig,
        retry_hook: Optional[RetryHook] = None,
        error_classifier: Optional[Callable[[Exception], TransportError]] = None,
        wrap_with_channel: bool = True
    ) -> 'IChannel': ...

    @classmethod
    def create(
        cls,
        config: TransportConfig,
        retry_hook: Optional[RetryHook] = None,
        error_classifier: Optional[Callable[[Exception], TransportError]] = None,
        wrap_with_channel: bool = False
    ) -> Union[BaseTransporter, 'IChannel']:
        """
        ينشئ ويهيئ ناقل L4 كامل بناءً على التكوين التصريحي.
        
        Args:
            config: تكوين النقل (Pydantic frozen)
            retry_hook: خطاف سياسة L5 صريح (أعلى أولوية من التكوين)
            error_classifier: دالة مخصصة لتصنيف الأخطاء (اختياري)
            wrap_with_channel: إذا True، يُغلّف الناقل بـ Channel لإدارة الحالة والمقاييس
            
        Returns:
            إذا wrap_with_channel=False: مثيل BaseTransporter جاهز للاستخدام
            إذا wrap_with_channel=True: مثيل IChannel (Channel مغلف) لإدارة دورة الحياة
            
        Raises:
            TransportFactoryError: لأخطاء التكوين الحرجة
        """
        # 1. التحقق من صحة التكوين (أخطاء التكوين → فشل فوري)
        if not isinstance(config, TransportConfig):
            raise TransportFactoryError("config must be an instance of TransportConfig")

        # 2. حل سياسة إعادة المحاولة (صريح > تصريحي > افتراضي)
        resolved_hook = cls._resolve_retry_hook(config, retry_hook)

        # 3. تهيئة محرك إعادة المحاولة (L4 Flow/Error Control)
        retry_engine = RetryEngine(
            config=config.retry_policy,
            hook=resolved_hook,
            error_classifier=error_classifier
        )

        # 4. تحديد الاتجاه
        direction = Direction.OUTBOUND if config.direction == "outbound" else Direction.INBOUND

        # 5. معالجة التوجيه المركب (Composite Routing)
        if config.transport_type == TransportType.COMPOSITE:
            transporter = cls._build_composite(
                config, retry_engine, resolved_hook, error_classifier, 
                wrap_children_with_channel=wrap_with_channel
            )
        else:
            # 6. اختيار الناقل الملموس وبناءه
            transporter = cls._resolve_and_build(config, direction, retry_engine)
        
        # 7. التغليف الاختياري بـ Channel (إذا طُلب)
        if wrap_with_channel:
            transporter = cls._wrap_with_channel(transporter, config.channel)
            logger.info(
                f"L4 Transport built + wrapped: type={config.transport_type.value}, "
                f"dir={direction.value}, channel_enabled=True"
            )
        else:
            logger.info(
                f"L4 Transport built: type={config.transport_type.value}, "
                f"dir={direction.value}, retry_attempts={config.retry_policy.max_attempts}, "
                f"hook={config.retry_policy.hook_type or 'default'}"
            )
        
        return transporter

    @classmethod
    def create_channel(
        cls,
        config: TransportConfig,
        retry_hook: Optional[RetryHook] = None,
        error_classifier: Optional[Callable[[Exception], TransportError]] = None
    ) -> 'IChannel':
        """
        طريقة مختصرة لإنشاء ناقل مغلف بـ Channel جاهز لإدارة الحالة والمقاييس.
        مكافئ لـ: create(config, retry_hook, error_classifier, wrap_with_channel=True)
        
        Returns:
            IChannel: واجهة موحدة لإدارة دورة حياة القناة
        """
        return cast('IChannel', cls.create(
            config=config,
            retry_hook=retry_hook,
            error_classifier=error_classifier,
            wrap_with_channel=True
        ))

    @classmethod
    def _wrap_with_channel(
        cls, 
        transporter: BaseTransporter, 
        channel_config: ChannelSettingsConfig
    ) -> 'IChannel':
        """يغلف ناقلًا ملموسًا بـ Channel لإضافة إدارة الحالة والمقاييس."""
        # Lazy import to avoid circular dependency
        from transport.channel import Channel
        return Channel(config=channel_config, transporter=transporter)

    @classmethod
    def _resolve_and_build(
        cls,
        config: TransportConfig,
        direction: Direction,
        retry_engine: RetryEngine
    ) -> BaseTransporter:
        """يحلل نوع النقل ويستدعي الدالة المناسبة من السجل أو المنطق الافتراضي."""
        transport_type = config.transport_type
        dir_str = direction.value

        # أ) استخدام السجل المسجل مسبقًا (إن وُجد)
        if dir_str in cls._builders.get(transport_type, {}):
            return cls._builders[transport_type][dir_str](config, retry_engine)

        # ب) البناء الافتراضي للمحولات القياسية (Lazy Import لمنع الدوائر)
        match transport_type:
            case TransportType.CLI:
                from transport.subprocess import SubprocessTransporter
                return SubprocessTransporter(
                    cmd=config.channel.subprocess_cmd or [],
                    env_overrides=config.channel.env_overrides,
                    retry_engine=retry_engine,
                    direction=direction
                )
            case TransportType.INPROCESS:
                from transport.inprocess import InProcessTransporter
                return InProcessTransporter(
                    retry_engine=retry_engine,
                    direction=direction
                    # يُتوقع أن يُحقن dispatcher/callable عبر استدعاء لاحق أو عبر إعدادات مخصصة
                )
            case TransportType.TCP:
                from transport.tcp import TCPTransporter
                host = "127.0.0.1"
                if config.channel.endpoint_url:
                    # دعم صيغ: "tcp://host:port" أو "host:port" أو "http://..."
                    host = config.channel.endpoint_url.split("://")[-1].split(":")[0]
                return TCPTransporter(
                    host=host,
                    port=config.channel.port or 0,
                    retry_engine=retry_engine,
                    direction=direction
                )
            case TransportType.UDS:
                from transport.uds import UDSTransporter
                return UDSTransporter(
                    socket_path=config.channel.socket_path or "/tmp/default.sock",
                    retry_engine=retry_engine,
                    direction=direction
                )
            case TransportType.WEBSOCKET:
                from transport.websocket import WebSocketTransporter
                # ✅ تصحيح #1: استخدام الأسماء الصحيحة من ChannelSettingsConfig
                ws_config = config.channel
                return WebSocketTransporter(
                    host=ws_config.endpoint_url or "127.0.0.1",
                    port=ws_config.port or 80,
                    path=ws_config.ws_path or "/",              # ← ws_path وليس path
                    retry_engine=retry_engine,
                    # ← timeout من retry_policy وليس من channel
                    timeout=config.retry_policy.initial_timeout or 30.0,
                    ping_interval=ws_config.ping_interval or 30.0,
                    pong_timeout=ws_config.pong_timeout or 10.0,
                    direction=direction
                )
            case TransportType.A2A:
                # A2A يُبنى عادةً كطبقة فوق TCP/HTTP + Registry. هنا نعيد TCP كقاعدة
                from transport.tcp import TCPTransporter
                logger.warning("A2A requested without custom builder. Falling back to TCP base transport.")
                return TCPTransporter(
                    host=config.channel.endpoint_url or "127.0.0.1",
                    port=config.channel.port or 0,
                    retry_engine=retry_engine,
                    direction=direction
                )
            case _:
                raise TransportFactoryError(f"Unsupported transport type: {transport_type}")

    @classmethod
    def _build_composite(
        cls,
        config: TransportConfig,
        parent_retry_engine: RetryEngine,
        retry_hook: Optional[RetryHook],
        error_classifier: Optional[Callable],
        wrap_children_with_channel: bool = False
    ) -> BaseTransporter:
        """
        يبني ناقلًا مركبًا يوجه الشرائح عبر قنوات متعددة مع الحفاظ على الترتيب.
        
        ✅ تصحيح #2: منع تغليف الأبناء بـ Channel في الوضع المركب حاليًا
        (CompositeTransporter يتوقع list[BaseTransporter]، وليس IChannel)
        """
        from transport.composite import CompositeTransporter, CompositeStrategy
        
        # ملاحظة: Composite يتطلب قائمة تكوينات فرعية. 
        # يمكن تمريرها عبر metadata أو حقل مخصص. هنا نستخدم نمطًا آمنًا.
        children_configs: List[Union[TransportConfig, Dict[str, Any]]] = config.channel.metadata.get("composite_children", [])
        if not children_configs:
            raise TransportFactoryError("COMPOSITE transport requires 'composite_children' in channel.metadata")

        children: List[BaseTransporter] = []
        for idx, child_cfg in enumerate(children_configs):
            # إعادة التحقق من نوع Pydantic
            if isinstance(child_cfg, dict):
                child = TransportConfig.model_validate(child_cfg)
            else:
                child = child_cfg  # Already a TransportConfig instance
            
            # ✅ تصحيح #2: نستخدم دائمًا create() (بدون تغليف) لضمان توافق CompositeTransporter
            if wrap_children_with_channel:
                logger.warning(
                    f"Channel wrapping for composite child[{idx}] is not yet supported. "
                    f"Falling back to raw BaseTransporter. "
                    f"See: CompositeTransporter expects list[BaseTransporter]"
                )
            
            child_transporter = cls.create(child, retry_hook, error_classifier, wrap_with_channel=False)
            children.append(child_transporter)
            logger.debug(f"Composite child[{idx}] built: type={child.transport_type.value}")

        strategy_str = config.channel.metadata.get("composite_strategy", "route")
        # تحويل السلسلة إلى Enum بشكل آمن
        strategy = CompositeStrategy.ROUTE
        for s in CompositeStrategy:
            if s.value == strategy_str.lower() or s.name.lower() == strategy_str.lower():
                strategy = s
                break
        
        logger.info(f"Composite built: strategy={strategy.value}, children={len(children)}")
        
        return CompositeTransporter(
            transporters=children,
            strategy=strategy
            # ملاحظة: CompositeTransporter لا يأخذ retry_engine في __init__ الحالي
            # إذا أُضيف هذا الدعم لاحقًا، يمكن تمريره هنا
        )

    @classmethod
    def get_supported_types(cls) -> List[TransportType]:
        """يعيد قائمة بأنواع النقل المدعومة حاليًا."""
        # الأنواع المدعومة افتراضيًا + أي نوع مسجل ديناميكيًا
        default_types = [
            TransportType.CLI,
            TransportType.INPROCESS,
            TransportType.TCP,
            TransportType.UDS,
            TransportType.WEBSOCKET,
            TransportType.A2A,
            TransportType.COMPOSITE
        ]
        return list(set(default_types + list(cls._builders.keys())))