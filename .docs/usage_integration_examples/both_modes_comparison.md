📊 مقارنة سريعة بين النمطين
البُعد
Embedded Mode
Gateway/Sidecar Mode
مكان التشغيل
نفس العملية/الذاكرة
عمليات منفصلة (حاويات/خوادم)
التأخير الداخلي
صفر (استدعاء دالة مباشر)
شبكي خفيف (HTTP/gRPC داخلي)
عزل الأعطال
عطل في الوكيل قد يؤثر على الفابريك إذا لم يُعزل جيدًا
عطل في الوكيل لا يؤثر على البوابة والعكس
نقطة التجميع
main.py واحد يربط كل شيء
fabric_service يجمع L3-L7، actor_service يستهلك فقط
كود BaseActor
✅ مطابق تمامًا
✅ مطابق تمامًا (يتم حقن RemoteAdapter بدل FabricClient)
حالة الاستخدام
خدمات مستقلة، وكلاء ذكيين، تطبيقات CLI/GUI
بيئات متعددة اللغات، سياسات أمان مركزية، مشاركة موارد الاتصال
🚀 كيف تشغّل الأمثلة؟

1- Embedded:

python examples/embedded_mode/main.py


2- Gateway:

# Terminal 1: تشغيل البوابة المركزية
uvicorn examples.gateway_mode.fabric_service.main:app --host 0.0.0.0 --port 8000

# Terminal 2: تشغيل الوكيل البعيد
python examples/gateway_mode/actor_service/main.py



✅ الخلاصة المعمارية
BaseActor نقي تمامًا. لا يعرف ChannelPool، SessionRegistry، HTTP، أو YAML.
التفاعل مع الفابريك يتم حصريًا عبر ICommunicationGateway.
تبديل نمط النشر = تغيير سطر واحد في Composition Root (حقن FabricClient أو RemoteAdapter).
هذا هو جوهر DIP + Composable Architecture: الكود يبقى ثابتًا، البنية التحتية تتغير عبر التكوين أو الحقن.


