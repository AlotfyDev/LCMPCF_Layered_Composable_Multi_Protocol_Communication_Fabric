ممتاز. بما أن العقود (`ISessionLifecycle` و `ICheckpointSync`) أصبحت مرجعًا مثبتًا، ننتقل الآن إلى **مخطط الربط المعماري (Binding Map)**. هذا المخطط يوضح بدقة كيف تتكامل طبقة الجلسة (L5) مع الناقل (L4) ومستوى الخدمة (`Actor-as-a-Service`)، مع الحفاظ على الحدود الصارمة لنموذج OSI.

---

## 🗺️ 1. مخطط الربط المفاهيمي (Conceptual Binding Map)

```
┌─────────────────────────────────────────────────────────────┐
│              Actor-as-a-Service (L7 Application)            │
│  • يملك منطق المجال، استدعاء الأدوات، توليد المحتوى         │
│  • يستهلك واجهتي L5 فقط (لا يعرف شيئًا عن L4)               │
└───────────────────────┬─────────────────────────────────────┘
                        │ 1. يطلب: SessionFactory.create(context, policy)
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                  SessionFactory (L5 Wiring)                 │
│  • يقرأ سياق النقل (CLI / InProcess / A2A)                  │
│  • يربط ISessionLifecycle + ICheckpointSync بالمحولات المناسبة│
│  • يغلفهما في UnifiedSessionManager موحد الواجهة            │
└───────────────────────┬─────────────────────────────────────┘
                        │ 2. يعيد كائنًا يطبق العقدين
                        ▼
┌─────────────────────────────────────────────────────────────┐
│           UnifiedSessionManager (L5 Session Layer)          │
│  • يدير: open/close, refresh, mark, restore, prune          │
│  • يعتمد على L4 كقناة تسليم صماء (Stateless Delivery)       │
│  • يضيف: SessionID, CorrelationID, Checkpoint Offsets       │
└───────────────────────┬─────────────────────────────────────┘
                        │ 3. يستدعي L4 للإرسال/الاستلام
                        ▼
┌─────────────────────────────────────────────────────────────┐
│            Transporter Factory / L4 Transport Layer         │
│  • ينفذ: segmentation, delivery, retry, flow control        │
│  • يظل غير واعٍ بمفاهيم الجلسة أو نقاط التفتيش              │
└───────────────────────┬─────────────────────────────────────┘
                        │ 4. تسليم الشرائح عبر القناة المادية
                        ▼
                   [Peer / LLM / Tool]
```

---

## 📐 2. قواعد الحدود والمسؤوليات (L4 vs L5 Binding Rules)

| المعيار | Layer 4 (Transport) | Layer 5 (Session) | قاعدة الربط |
|---------|---------------------|-------------------|-------------|
| **الوعي بالسياق** | لا يعرف `SessionID` أو `Checkpoint` | يعرف `SessionID`، `Offset`، `State` | L5 يغلّف استدعاءات L4 ويضيف وسوم سياق، لكن L4 يعامل الحمولة كـ `bytes` عمياء |
| **إدارة الأخطاء** | يعيد إرسال الشرائح المفقودة (`RetryPolicy`) | يقرر *من أين* يستأنف الحوار بعد فشل L4 المتكرر | L4 يُبلغ الفشل → L5 يقرر `restore()` أو `close()` → L7 يتخذ الإجراء |
| **دورة الحياة** | يفتح/يغلق قناة تسليم عند كل عملية إرسال | يفتح/يغلق حوارًا منطقيًا قد يمتد عبر عدة قنوات L4 | L5 يستدعي L4 عند `open()`، لكن قد يعيد ربط قناة L4 جديدة دون إنهاء الجلسة |
| **المزامنة** | يتحكم في سرعة الإرسال والتدفق | يدرج نقاط تفتيش، يتتبع الترتيب المنطقي للرسائل | L5 يمرر `checkpoint.mark()` قبل/أثناء إرسال L4، ويستخدم `offset` لمطابقة الاستئناف |

> ✅ **القاعدة الذهبية**: L4 مسؤول عن *"هل وصلت البايتات؟"*، L5 مسؤول عن *"هل لا يزال الحوار صالحًا؟ وأين توقفنا؟"*. لا تداخل، ولا اقتران.

---

## 🔌 3. مصفوفة الربط حسب سياق النقل (Context Wiring Matrix)

| السياق | مكافئ OSI L4 (الناقل) | مكافئ OSI L5 (الجلسة) | آلية الربط (Binding Mechanism) |
|--------|----------------------|----------------------|-------------------------------|
| **CLI** | `SubprocessTransporter` (stdin/stdout/stderr) | `ProcessSessionAdapter` + `FileCheckpointAdapter` | الجلسة مرتبطة بعمر العملية (`PID`). نقاط التفتيش تُحفظ في ملفات مؤقتة مع تتبع `stream_offset`. عند إعادة التشغيل، يُقرأ آخر ملف استئناف. |
| **InProcess** | `InProcessTransporter` (استدعاء دالة مباشر) | `ContextSessionAdapter` + `MemoryCheckpointAdapter` | الجلسة مرتبطة بـ `async context` أو `thread`. نقاط التفتيش كائنات في الذاكرة أو لقطات `Pydantic`. المزامنة عبر `Locks` محلية. |
| **A2A** | `TCPTransporter` / `HTTPTransporter` | `NetworkSessionAdapter` + `DistributedCheckpointAdapter` | الجلسة كيان منطقي عبر `Session-ID` في الهيدر أو إطار WebSocket. نقاط التفتيش في مخزن موزع (Redis/DB). الاستئناف عبر تفاوض بروتوكولي (`206 Partial Resume`). |

---

## 🔁 4. تدفق التفاعل خطوة بخطوة (Interaction Flow)

1. **التهيئة**: `Actor` يستدعي `session.open(config)` → L5 يولد `SessionID`، يطلب من L4 فتح قناة، يسجل `created_at`.
2. **الإرسال المستمر**: مع كل دفعة بيانات، يستدعي `session.refresh()` → L5 يعيد ضبط `idle_timeout`، يمرر البيانات لـ L4.
3. **إدراج نقطة تفتيش**: عند عبور عتبة حجمية أو زمنية، يستدعي `checkpoint.mark(payload, offset)` → L5 يحفظ الحالة، يعيد `CheckpointID`.
4. **انقطاع/عطل في L4**: يفشل `RetryPolicy` بعد المحاولات القصوى → L4 يرفع `TransportError` → L5 يكتشف الانقطاع، يستدعي `checkpoint.get_latest()`.
5. **الاستئناف**: `Actor` يطلب `session.restore(checkpoint_id)` → L5 يعيد `payload` + `offset` → يوجه L4 للإرسال من `offset` الجديد.
6. **الإنهاء**: عند اكتمال التبادل، يستدعي `session.close()` → L5 ينهي العدادات، يحذف نقاط التفتيش الزائدة (`prune`)، يوجه L4 لإغلاق القناة.

---

## ⚙️ 5. مخطط التكوين والمصنع (Factory & Config Schema)

لجعل الربط قابلًا للتكوين دون تعديل الكود، نعتمد نمطًا سياسيًا بسيطًا:

```yaml
session_policy:
  transport_context: "cli" | "inprocess" | "a2a"
  lifecycle:
    ttl_seconds: 3600
    idle_timeout: 300
    auto_close_on_success: true
  checkpoint:
    interval_bytes: 5242880  # 5MB
    interval_seconds: 30
    max_history: 10
    storage_backend: "file" | "memory" | "redis" | "sqlite"
  binding_rules:
    on_transport_failure: "restore_latest" | "close_session"
    on_timeout: "refresh_and_retry" | "terminate"
```

`SessionFactory` يقرأ هذا التكوين، ويختار المحولات المطابقة، ويربطها بـ L4 الحالي، ثم يعيد `UnifiedSessionManager` جاهزًا للحقن في `BaseActor`.

---
