بناءً على التصميم المعماري الذي اتفقنا عليه لطبقة العرض (L6)، إليك القائمة الدقيقة والملزمة للتنفيذ:

---

### 📁 1. ملفات جديدة مطلوبة (New Files)
| المسار | الدور المعماري | المحتوى المتوقع |
|--------|---------------|----------------|
| `presentation/protocol.py` | عقود مجردة (Abstract Contracts) | تعريف `ISerializer`, `IStreamCodec`, `ICompressor` كبروتوكولات `typing.Protocol` محايدة الاتجاه |
| `presentation/codecs/__init__.py` | تجميع محولات الترميز | تصدير موحد للمحولات: `JsonSerializer`, `SSEStreamCodec`, `ZstdCompressor` |
| `presentation/codecs/json_serializer.py` | `SchemaSerializer` تنفيذ | يحول `BaseModel ↔ bytes` مع دعم `JSON`/`MessagePack`، والتحقق الصارم قبل الترميز |
| `presentation/codecs/sse_stream_codec.py` | `StreamCodec` تنفيذ | يغلّف `sse_parser.py` الحالي، ويضيف `encode_stream(async_gen) → bytes_stream` و `decode_stream(bytes_iter) → async_gen` |
| `presentation/codecs/compression.py` | `CompressionAdapter` تنفيذ | غلاف خفيف لـ `gzip`/`zstd` مع تفعيل/تعطيل شرطي حسب `direction` وحجم الحمولة |
| `presentation/pipeline.py` | `PresentationPipeline` منسق | يقرأ `Direction` و`config`، يرتب المكونات (`serialize → compress` أو العكس)، ويتجاوز المعالجة كليًا عند `INPROCESS` |

---

### 🔄 2. ملفات قائمة تحتاج تحديثًا (Existing Files to Update)
| الملف | طبيعة التحديث | السبب المعماري |
|-------|--------------|----------------|
| `presentation/request_types.py` | **توثيق ومحاذاة فقط** (لا تغيير هيكلي) | يُعرّف كمصدر المخططات (`BaseModel`) التي يستهلكها `SchemaSerializer`. قد تُضاف وسوم اختيارية مثل `json_schema_extra` أو `model_config` لتحسين الترميز، لكن لا يُكسر التوافق العكسي |
| `presentation/sse_parser.py` | **إعادة تغليف أو نقل منطقي** | حاليًا محلل أحادي الاتجاه. يجب دمجه داخل `sse_stream_codec.py` كدالة `decode_stream`، أو تحديثه ليصدر كلاس `SSEStreamCodec` يطبق `IStreamCodec` ثنائي الاتجاه |
| `presentation/__init__.py` | **تحديث الصادرات العامة** | يعرض فقط الواجهة الموحدة: `PresentationPipeline`, `SchemaSerializer`, `StreamCodec`, `Compressor`. يخفي `codecs/` و `protocol.py` الداخلية لضمان نظافة الـ Public API |

---

### 📝 3. طبيعة التعديلات المطلوبة (Nature of Changes)
| النوع | الوصف | الأثر على الكود الحالي |
|-------|-------|------------------------|
| 🔹 **إضافة عقود مجردة** | فصل الواجهة (`protocol.py`) عن التنفيذ (`codecs/`) | لا يؤثر على الملفات القائمة، يضيف طبقة DIP جديدة |
| 🔹 **أغلفة تنفيذية (Codecs)** | تحويل النماذج والدفقات إلى/من `bytes` مع دعم ضغط شرطي | ملفات جديدة في `codecs/`، لا تعديل مباشر على `request_types.py` |
| 🔹 **منسق اتجاهي (Pipeline)** | يقرأ `Direction`، يرتب التنفيذ، ويتجاوز لـ `INPROCESS` | ملف جديد `pipeline.py`، يعتمد على `protocol.py` و `codecs/` |
| 🔹 **محاذاة توثيقية** | ربط `request_types.py` و `sse_parser.py` بالهيكل الجديد | لا كسر توافق، فقط إعادة توجيه الاستيرادات وتحديث `__init__.py` |

---

### ✅ ملاحظة معمارية حاسمة
- **`INPROCESS` Bypass**: عند `direction == Direction.INPROCESS`، يعيد `PresentationPipeline` الدالة/البيانات كما هي (`Identity Transform`) لأن L6 غير مطلوب محليًا حسب OSI، مما يوفر تأخيرًا صفريًا ويحافظ على كفاءة الذاكرة.
- **الاتجاهية**: العقد (`protocol.py`) **محايدة تمامًا**. الاتجاه يتحكم فقط في **ترتيب الاستدعاء** داخل `pipeline.py`، وليس في تعريف المكونات نفسها.
- **التوافق العكسي**: `request_types.py` و `sse_parser.py` يبقیان صالحين للاستهلاك المباشر أثناء المرحلة الانتقالية، لكن يُوجَّه المستهلكون الجدد لاستخدام `PresentationPipeline`.

---

هل تريد أن أبدأ فورًا بصياغة **`presentation/protocol.py`** (العقود المجردة) كخطوة أولى، ثم الانتقال إلى `codecs/` و `pipeline.py` بالترتيب البنيوي؟