🛠️ كيفية التشغيل والإثبات العملي
1️⃣ تشغيل البيئة
bash

# تشغيل الفابريك في الخلفية
docker compose up -d --build

# مراقبة السجلات حتى يظهر "Fabric assembled successfully"
docker compose logs -f comm-fabric


2️⃣ تشغيل الاختبارات


# تثبيت متطلبات الاختبار
pip install pytest pytest-asyncio httpx

# تشغيل اختبارات العزل فقط (سريعة، لا تحتاج Docker)
pytest tests/test_actor_isolation.py -v

# تشغيل اختبارات التكامل (تحتاج Docker شغال)
pytest tests/test_fabric_integration.py -m integration -v



📊 الناتج المتوقع عند النجاح


✅ test_live_protocol_switch_http_to_graphql PASSED
✅ test_health_endpoints_consistency PASSED
✅ test_execute_task_success_and_cleanup PASSED
...
6 passed, 0 failed, 100% contract compliance verified



✅ ماذا يثبت هذا الاختبار معماريًا؟
المعيار
الإثبات في الكود
تبديل بروتوكول حي
نفس session_id ينتقل من http → graphql دون إعادة إنشاء جلسة أو فقدان سياق
ثبات الجاهزية
/ready يعيد 200 OK باستمرار لأن PipelineRegistry يدير الخطوط بشكل مستقل، والتبديل لا يوقف التجميع
معايير K8s/Cloud
/live, /ready, /health تستجيب بالأكواد والحقول المتوقعة، جاهزة لـ livenessProbe و readinessProbe
تنظيف آمن
close_session يُطلق الموارد، ولا يؤثر على جاهزية النظام الكلية
عزل الاختبارات
conftest.py يزيل التكرار، و@pytest.mark.integration يفصل الاختبارات الشبكية عن الوحدة



