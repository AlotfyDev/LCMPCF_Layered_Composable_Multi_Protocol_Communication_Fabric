أنت محق تمامًا، وتصحيحك يلامس صلب الدقة المعمارية. تحديث الموجودات هو **نصف المهمة**، والنصف الآخر هو **رسم خريطة الفجوات البروتوكولية (L7 Gap Analysis)** على المستويين الشبكي والمحلي، ثم سدّها بعقود متوافقة مع OSI.

إليك التحليل الهيكلي الكامل لطبقة البروتوكولات (L7)، مقسمًا إلى: **تحديث الحالي**، **كشف المفقود**، و**العقد الموحد** الذي سيضمن تكاملهم جميعًا.

---

### 📊 مصفوفة الفجوات والإضافات المطلوبة (OSI L7 Application Protocols)

| المستوى | البروتوكول | الملف الحالي | الحالة الحالية | الإجراء المطلوب | الدور المعماري (L7 Semantics) |
|---------|------------|--------------|----------------|----------------|-------------------------------|
| 🔵 **شبكي** | HTTP/REST | `http.py` | ✅ موجود لكنه ينفذ تسلسل يدويًا | 🔹 تحديث → `HttpProtocolHandler` | التفاوض على `Accept/Content-Type`، تعيين `Status Codes`، تمرير الحمولة لـ L6، ربط الأخطاء بـ `ProtocolErrorMapper` |
| 🔵 **شبكي** | GraphQL | ❌ مفقود | غير موجود | 🔹 إنشاء → `GraphqlProtocolHandler` | تحليل `query/variables/operationName`، تنسيق أخطاء GraphQL Spec (`{errors: [{message, path}]}`)، دعم `GET` للـ Queries و `POST` للـ Mutations |
| 🔵 **شبكي** | gRPC | `grpc.py` | ⚠️ هيكل أولي غير مكتمل | 🔹 إكمال → `GrpcProtocolHandler` | إدارة `metadata`/`trailers`، تعيين `grpc-status`/`grpc-message`، نقطة ربط مستقبلية لـ L6 `ProtobufCodec` |
| 🔵 **شبكي** | WebSocket (App Layer) | ❌ مفقود | L4 يدير الإطارات فقط | 🔹 إنشاء → `WsProtocolHandler` | تفاوض `Sec-WebSocket-Protocol`، تفسير `Close Codes` تطبيقيًا، توجيه أحداث `ping/pong` لمستوى التطبيق، دعم Subprotocols مثل `graphql-ws` أو `a2a-v1` |
| 🟢 **محلي** | CLI/Subprocess | `cli.py` | ✅ موجود لكنه يدير `subprocess` مباشرة | 🔹 تحديث → `CliProtocolHandler` | حقن `env` من `TransportContext`، تأطير `stdin/stdout`، تحويل `exit_code` إلى حالة بروتوكول، توجيه `stderr` كـ `ProtocolError` |
| 🟢 **محلي** | InProcess | ❌ مفقود | غير موجود | 🔹 إنشاء → `InProcessProtocolHandler` | جسر تنفيذ `Callable` متزامن/غير متزامن، تمرير `TransportContext` صريحًا، تحويل استثناءات بايثون إلى كود حالة موحد، عزل الذاكرة المشتركة |
| 🟡 **عابر** | Error Mapping | `http_errors.py` | مقيد بـ HTTP فقط | 🔹 تحديث → `ProtocolErrorMapper` | ترجمة موحدة لـ `PresentationError`/`TransportError`/`App Exceptions` → صيغ بروتوكولية (`HTTP JSON`, `GraphQL errors`, `gRPC Status`, `CLI exit`) |

---

### 🏗️ العقد الموحدة المقترحة لـ L7 (`IProtocolHandler`)
لضمان أن كل معالج بروتوكول (سواء شبكي أو محلي) يتكامل بسلاسة مع L4/L5/L6، نعرّف عقدًا أساسيًا واحدًا:

```python
# protocols/base.py
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Optional
from transport.context import TransportContext
from presentation.pipeline import PresentationPipeline

class IProtocolHandler(ABC):
    @abstractmethod
    async def handle_inbound(
        self, 
        raw_input: bytes | AsyncIterator[bytes], 
        context: TransportContext,
        pipeline: PresentationPipeline
    ) -> bytes | AsyncIterator[bytes]:
        """يستقبل بيانات خام من L4، يفكها برمجياً، يعالجها تطبيقياً، ويعيد صياغتها للخارج."""
        ...

    @abstractmethod
    async def handle_outbound(
        self, 
        app_payload: Any, 
        context: TransportContext,
        pipeline: PresentationPipeline
    ) -> bytes | AsyncIterator[bytes]:
        """يأخذ نتيجة التطبيق، يغلفها ببروتوكول L7، ويجهزها للإرسال عبر L6/L4."""
        ...
```
✅ هذا العقد يضمن أن **كل بروتوكول يتحدث نفس اللغة مع الطبقات الأدنى والأعلى**، دون اقتران بتفاصيل النقل أو التسلسل.

---

### 🔄 خطة التنفيذ المقترحة (حسب الاعتمادية البنيوية)
1. ✅ **تحديث `http_errors.py` → `ProtocolErrorMapper`** (الأساس المشترك لجميع البروتوكولات)
2. ✅ **تحديث `cli.py` → `CliProtocolHandler`** (إكمال المستوى المحلي الأساسي)
3. ✅ **إنشاء `inprocess.py` → `InProcessProtocolHandler`** (سد فجوة الذاكرة المشتركة)
4. ✅ **تحديث `http.py` → `HttpProtocolHandler`** + **إنشاء `graphql.py` → `GraphqlProtocolHandler`** (المستوى الشبكي الرئيسي)
5. ✅ **تحديث `grpc.py`** + **إنشاء `ws_protocol.py`** (البروتوكولات المتقدمة)

---

### 🎯 سؤال التوجيه
لأي ملف تفضل أن نبدأ **فورًا**؟
1. 🔹 `ProtocolErrorMapper` (يؤسس توحيد الأخطاء لكل ما يليه)
2. 🔹 `InProcessProtocolHandler` (يُكمل فجوة المستوى المحلي قبل الشبكي)
3. 🔹 `GraphqlProtocolHandler` (يغطي الفجوة الشبكية الأكثر طلبًا في سياق الوكلاء)
4. 🔹 تحديث `HttpProtocolHandler` أولًا كمرجعية قياسية

