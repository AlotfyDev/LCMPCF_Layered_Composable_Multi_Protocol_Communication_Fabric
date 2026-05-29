✅ لماذا يحقق هذا التصميم رؤية "الفهرسة والتجميع الميكانيكي"؟
المبدأ
التطبيق في الكود
عزل التبعيات
LayerRegistry لا يعرف تفاصيل التنفيذ. يخزن مراجع كائنات فقط ويوفر واجهات وصول واضحة (get_network_pool, get_session_dispatcher إلخ)
فهرسة مركبة ذكية
PipelineRegistry يستخدم (direction, protocol) كمفتاح فريد، مما يمكّن من تشغيل عدة خطوط لنفس البروتوكول باتجاهات مختلفة دون تعارض
أمان متزامن صارم
جميع العمليات الحرجة محمية بـ asyncio.Lock. يمنع السباقات أثناء التسجيل، الاسترجاع، أو الإغلاق المتزامن
دورة حياة واضحة
close() يُنفذ بترتيب عكسي للتسجيل، ويتحقق من asyncio.iscoroutinefunction لدعم كل من async def close و def close دون أخطاء
مراقبة وتصحيح مدمج
list_registered() و get_stats() يعيدان حالة السجل لحظيًا، مما يسهل التكامل مع Prometheus/Grafana أو السجلات الداخلية
جاهز لـ Assembler
الواجهات بسيطة وصريحة. Assembler يبني → Registry يخزن → BaseActor/FastAPI يستعلم. لا اقتران، لا Globals مخفية
🔄 كيف يندمج في ActorAssembler؟


# wiring/assembler.py (مقتطف مستقبلي)
registry = LayerRegistry()
pipe_registry = PipelineRegistry()

# 1. تجميع المكونات
await registry.register("network", "channel_pool", pool)
await registry.register("session", "dispatcher", dispatcher)
await registry.register("presentation", "pipeline", pipeline)
await registry.register("protocol", "http", http_handler)

# 2. تجميع الخطوط الاتجاهية
out_pipe = OutboundCommunicationPipeline(pipeline, dispatcher, http_handler)
in_pipe = InboundCommunicationPipeline(pipeline, dispatcher, http_handler)

# 3. فهرسة الخطوط
await pipe_registry.register("outbound", "http", out_pipe)
await pipe_registry.register("inbound", "http", in_pipe)

# 4. الاستخدام لاحقًا
http_out = await pipe_registry.get("outbound", "http")
await http_out.send(payload, session_id="x")