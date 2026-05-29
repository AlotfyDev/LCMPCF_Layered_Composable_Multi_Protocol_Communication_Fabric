✅ لماذا يحقق هذا التصميم رؤيتك "الميكانيكية والاتجاهية"؟
المبدأ
التطبيق في الكود
اتجاهية صارمة
Outbound يدير Application → Network. Inbound يدير Network → Application. لا تداخل في المسؤولية.
عزل طبقي آلي
كل طبقة تُستدعى صراحةً عبر _wrap_execution. الأخطاء تُغلّف بـ PipelineExecutionError مع تحديد الطبقة الفاشلة.
إدارة موارد ميكانيكية
dispatcher.route_session()، dispatcher.touch()، dispatcher.release_session() تُدار تلقائيًا قبل/بعد/أثناء التنفيذ.
دعم البث المتدفق
_stream_send() و receive_stream() يعيدان AsyncIterator[Any] مع عزل أخطاء لكل شريحة دون كسر التدفق الكلي.
جاهز للتجميع الديناميكي
يعتمد فقط على حقن PresentationPipeline, SessionDispatcher, ProtocolHandler. يمكن تجميعه من YAML عبر ActorAssembler.
مراقبة وإحصائيات مدمجة
_stats تتبع عدد الطلبات، الأخطاء، ومتوسط الكمون تلقائيًا لكل خط اتجاهي.
🔄 كيف يندمج في ActorAssembler لاحقًا؟
python


# wiring/assembler.py (مقتطف)
outbound_pipeline = OutboundCommunicationPipeline(
    presentation=presentation_pipeline,
    dispatcher=session_dispatcher,
    protocol_handler=protocol_provider.get_handler("http", Direction.OUTBOUND)
)
inbound_pipeline = InboundCommunicationPipeline(
    presentation=presentation_pipeline,
    dispatcher=session_dispatcher,
    protocol_handler=protocol_provider.get_handler("http", Direction.INBOUND)
)
pipeline_registry.register("outbound", "http", outbound_pipeline)