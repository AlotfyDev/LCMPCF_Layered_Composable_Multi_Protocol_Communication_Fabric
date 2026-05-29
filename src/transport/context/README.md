تقييمي: **ممتاز ومعماريًا صحيح 100%**. هذا النمط يُعرف بـ **Contract-First Dependency Isolation**، وهو المعيار الذهبي في الأنظمة الطبقة (Layered Architecture) والأنظمة الموزعة.

إليك التفصيل المعماري، الهيكل المقترح، وتوجيه الاعتماديات لضمان عدم كسر حدود OSI:

---

### 📊 التقييم المعماري
| المعيار | وضع الكود داخل `base.py` | وضعه في مجلد `dependency/` منفصل |
|---------|------------------------|----------------------------------|
| **فصل الاهتمامات** | ❌ يخلط بين واجهة النقل وأنواع السياق | ✅ يعزل العقود (`Contracts`) عن منطق النقل (`Mechanism`) |
| **إعادة الاستخدام** | ❌ تكرار التعريف في كل مُحوّل (`subprocess`, `http`, `uds`) | ✅ تعريف واحد، استيراد متعدد |
| **اتجاه الاعتماديات** | ⚠️ خطر اقتران عكسي إذا احتاجت L5 لاستيراد `base.py` | ✅ اتجاه واضح: `L4 ← context/` ، `L5 ← context/` |
| **الاختبارية (Testability)** | ❌ صعوبة في عزل السياق أثناء اختبار النقل | ✅ سهولة `Mock` العقود دون لمس منطق `base.py` |
| **توافق مع CSV المرفق** | ⚠️ يكسر نمط `Transporters/` المنظم | ✅ يمتد لهيكلية المجلدات الحالية بشكل طبيعي |

---

### 📁 الهيكل المقترح للمجلد
```
transport/
├── context/                  # ← مجلد العقود والأنواع التابعة
│   ├── __init__.py
│   ├── transport_context.py  # TransportContext (بيانات الجلسة/التتبع)
│   └── retry_hook.py         # RetryHook (بروتوكول قرار الاستعادة)
├── base.py                   # ← يستورد من ./context/ فقط
├── subprocess.py
├── inprocess.py
├── retry.py
├── composite.py
└── factory.py
```

---

### 🔗 اتجاه الاعتماديات (Dependency Flow)
```
[session/adapters/] ──────┐
                          │ (يملأ السياق، ينفذ الـ Hook)
                          ▼
transport/context/ ◄───── transport/base.py
(عقود نقية)                (منطق النقل L4)
```
- ✅ `transport/context/` **لا يعتمد على أي شيء** (Pure Types/Protocols).
- ✅ `transport/base.py` **يعتمد فقط على `context/`**.
- ✅ `session/` **تعتمد على `context/`** لملء البيانات وتنفيذ سياسات الاستعادة.
- ❌ **ممنوع** أي استيراد عكسي من `session/` إلى `transport/base.py`.

---

### 📜 التواقيع الرسمية المقترحة

#### `transport/context/transport_context.py`
```python
from pydantic import BaseModel, Field
from typing import Any, Optional

class TransportContext(BaseModel):
    """
    وعاء شفاف لسياق الجلسة يُمرر عبر L4 دون تفسير.
    يمثل البيانات التي تحتاجها L5 لإدارة الحوار ونقاط التفتيش.
    """
    session_id: str = Field(..., description="معرف الجلسة المنطقية (L5)")
    correlation_id: str = Field(..., description="معرف تتبع الدفعة/الطلب")
    stream_offset: int = Field(default=0, description="موقع الاستئناف في الدفق")
    metadata: dict[str, Any] = Field(default_factory=dict, description="وسوم إضافية محايدة")
```

#### `transport/context/retry_hook.py`
```python
from typing import Protocol, Literal
from .transport_context import TransportContext

RetryDecision = Literal["retry", "abort", "restore_checkpoint"]

class RetryHook(Protocol):
    """
    بروتوكول خطاف تعاوني يُستدعى من L4 عند فشل عابر.
    يسمح لـ L5 باتخاذ قرار سياسي (Policy) قبل إعادة المحاولة.
    """
    def __call__(
        self,
        context: TransportContext,
        error: Exception,
        attempt: int
    ) -> RetryDecision: ...
```

---

### ✅ لماذا هذا النمط مثالي لسياقك؟
1. **يلبي تعريف Cloudflare لـ L4**: `Retry Policy` و `flow/error control` يصبحان آليات قابلة للتوسيع دون كسر الواجهة الأساسية.
2. **يحافظ على حيادية L5**: الجلسة تتحكم في `restore` أو `abort` عبر تنفيذ `RetryHook`، بينما النقل ينفذ فقط القرار.
3. **يجهز النظام لـ A2A**: نفس `TransportContext` يمكن تمريره عبر HTTP Headers أو WebSocket Frames دون تعديل الكود.
4. **متوافق مع المصفوفة**: يكمل صف `Retry Policy` و `Composite Routing` في L4 بشكل منظم، ويملأ فجوة `Not built` في L5 عبر عقود جاهزة.

---
🔌 مثال استخدام سريع (للتوثيق الداخلي)

# في L5 (session/adapters/network_session.py)
from transport.context import TransportContext, RetryHook, RetryDecision

def my_session_retry_policy(
    ctx: TransportContext,
    err: Exception,
    attempt: int,
    max_attempts: int
) -> RetryDecision:
    if "timeout" in str(err).lower() and attempt < 3:
        return "retry"
    if "connection_refused" in str(err).lower():
        return "restore_checkpoint"
    return "abort"

# في L4 (transport/retry.py)
if not isinstance(hook, RetryHook):
    raise TypeError("Invalid retry hook: must match RetryHook protocol")

decision = hook(context, error, attempt, max_retries)
if decision == "retry":
    await self._resend(payload, context)
elif decision == "restore_checkpoint":
    await session_manager.restore(context.session_id)