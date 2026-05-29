# presentation/protocol.py
"""
OSI Layer 6 Presentation Contracts (Abstract Protocols).
مسؤوليته حصريًا: تعريف واجهات محايدة للترجمة (Translation)، الضغط (Compression)،
وترميز التدفقات (Stream Encoding/Decoding).

Design Principles:
- Protocol-based (Structural Subtyping): لا وراثة هرمية، فقط توافق في التوقيع.
- Generic & Type-Safe: استخدام TypeVar لضمان التحقق من الأنواع أثناء التطوير.
- Direction Agnostic: لا يعرف Inbound أو Outbound، يركز على التحويل النقي فقط.
"""
from __future__ import annotations

from typing import (
    Any,
    AsyncIterator,
    Generic,
    Protocol,
    TypeVar,
)

# متغير نوعي لتمثيل الحمولة (Payload) بشكل عام
T = TypeVar("T")


class PresentationError(Exception):
    """
    استثناء أساسي لعمليات طبقة العرض (Translation/Compression).
    يُستخدم لعزل أخطاء الترميز عن أخطاء النقل (L4) أو منطق التطبيق (L7).
    """
    pass


class ISerializer(Protocol[T]):
    """
    بروتوكول التحويل بين الكائنات التطبيقية والتمثيل الثنائي (Translation).
    مسؤول عن: Serialize (Object → Bytes) و Deserialize (Bytes → Object).
    
    ملاحظات معمارية:
    - مصمم للعمل مع أي بنية بيانات (Pydantic, Dicts, Dataclasses).
    - محايد تمامًا: لا يعتمد على بروتوكول نقل (HTTP, TCP, etc).
    """

    def serialize(self, obj: T) -> bytes:
        """
        يحوّل كائنًا تطبيقيًا إلى تسلسل بايتات جاهز للنقل.
        
        Args:
            obj: الكائن المراد ترميزه.
        Returns:
            bytes: التمثيل الثنائي للكائن.
        Raises:
            PresentationError: في حال فشل الترميز.
        """
        ...

    def deserialize(self, data: bytes, target_type: type[T]) -> T:
        """
        يفك تشفير بايتات ويعيدها إلى كائن تطبيقي من النوع المطلوب.
        
        Args:
            data: البيانات الثنائية الخام.
            target_type: الفئة المستهدفة لإعادة البناء (إلزامي لضمان الدقة).
        Returns:
            T: الكائن المعاد بناؤه.
        Raises:
            PresentationError: في حال فشل فك الترميز أو عدم تطابق المخطط.
        """
        ...


class IStreamCodec(Protocol):
    """
    بروتوكول ترميز وفك ترميز التدفقات غير المتزامنة (Stream Translation).
    مسؤول عن: تحويل AsyncIterator للكائنات إلى AsyncIterator للبايتات، والعكس.
    
    ملاحظات معمارية:
    - يُستخدم مع تنسيقات البث مثل SSE، NDJSON، أو WebSocket frames.
    - يحافظ على حدود الرسائل (Message Boundaries) أثناء التحويل.
    """

    def encode_stream(self, object_stream: AsyncIterator[Any]) -> AsyncIterator[bytes]:
        """
        يحوّل تدفق كائنات إلى تدفق بايتات مع تحديد الحدود (Framing).
        
        Args:
            object_stream: المصدر (تدفق الكائنات).
        Yields:
            bytes: شرائح البيانات المرمزة.
        """
        ...

    def decode_stream(self, byte_stream: AsyncIterator[bytes]) -> AsyncIterator[Any]:
        """
        يفك ترميز تدفق بايتات ويعيده كدفق كائنات مرتبة.
        
        Args:
            byte_stream: المصدر (تدفق البايتات).
        Yields:
            Any: الكائنات المفككة.
        """
        ...


class ICompressor(Protocol):
    """
    بروتوكول ضغط وفك ضغط الحمولات الثنائية (Compression).
    مسؤول عن: تقليل حجم البيانات قبل النقل، واستعادتها بدقة عند الاستلام.
    
    ملاحظات معمارية:
    - يجب أن يكون متماثلًا رياضيًا: decompress(compress(data)) == data
    - يُفعّل اختياريًا عبر التكوين، ويُتجاوز تلقائيًا في سيناريوهات InProcess.
    """

    def compress(self, data: bytes) -> bytes:
        """يضغط حمولة بايتية لتقليل حجمها."""
        ...

    def decompress(self, data: bytes) -> bytes:
        """يفك ضغط حمولة بايتية لاستعادة البيانات الأصلية."""
        ...