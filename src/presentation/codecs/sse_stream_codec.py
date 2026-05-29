# presentation/codecs/sse_stream_codec.py
"""
OSI Layer 6 SSE Stream Codec (Stream Translation & Framing).
مسؤوليته حصريًا: تحويل AsyncIterator للكائنات ↔ AsyncIterator للبايتات بتنسيق SSE.
يطبق عقد IStreamCodec، ويعزل تعقيد الحدود (Framing) عن المنطق التطبيقي.
حالة صفرية لكل تدفق (Stateless per stream)، محايد للاتجاه، وقابل للحقن في Pipeline.
"""
from __future__ import annotations

import json
from typing import Any, AsyncIterator

from presentation.protocol import IStreamCodec, PresentationError


class SSEStreamCodec(IStreamCodec):
    """
    مُحوّل تدفقات SSE (OSI L6 Stream Translation).
    يحوّل الكائنات إلى إطارات SSE (`data: ...\n\n`) والعكس، مع دعم آمن للتسليم المتقطع (Chunked Delivery).
    """

    def __init__(self, auto_json: bool = True):
        """
        يهيئ محول التدفق بخيارات تحويل ذكية.
        
        Args:
            auto_json: إذا True، يحاول تلقائيًا تحليل/توليد JSON من/إلى الكائنات.
        """
        self.auto_json = auto_json

    async def encode_stream(self, object_stream: AsyncIterator[Any]) -> AsyncIterator[bytes]:
        """
        يحوّل تدفق كائنات إلى تدفق بايتات SSE مع تحديد الحدود (\n\n).
        
        Args:
            object_stream: المصدر غير المتزامن للكائنات التطبيقية.
        Yields:
            bytes: إطارات SSE جاهزة للنقل عبر L5/L4.
        """
        async for obj in object_stream:
            try:
                if isinstance(obj, bytes):
                    data_str = obj.decode("utf-8", errors="replace")
                elif self.auto_json:
                    data_str = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
                else:
                    data_str = str(obj)
                # SSE spec: data: field + \n\n boundary
                yield f"data: {data_str}\n\n".encode("utf-8")
            except Exception as e:
                raise PresentationError(f"SSE encode failed for object: {e}") from e

    async def decode_stream(self, byte_stream: AsyncIterator[bytes]) -> AsyncIterator[Any]:
        """
        يفك ترميز تدفق بايتات SSE ويعيده كدفق كائنات.
        يتعامل مع التسليم المتقطع (Chunked) عبر Buffer داخلي آمن.
        
        Args:
            byte_stream: المصدر غير المتزامن لشرائح البايتات.
        Yields:
            Any: الكائنات المفككة (dict, str, أو bytes حسب المحتوى).
        """
        buffer = b""
        async for chunk in byte_stream:
            buffer += chunk
            # استخراج الرسائل المكتملة عند حد \n\n
            while b"\n\n" in buffer:
                raw_msg, buffer = buffer.split(b"\n\n", 1)
                yield self._parse_sse_frame(raw_msg)
        
        # معالجة أي بيانات متبقية في الـ buffer عند انتهاء الدفق
        if buffer.strip():
            yield self._parse_sse_frame(buffer)

    def _parse_sse_frame(self, raw_frame: bytes) -> Any:
        """
        يحلل إطار SSE خام ويستخرج محتوى حقل data:.
        يدعم حقول data: متعددة الأسطر حسب مواصفات SSE.
        """
        try:
            text = raw_frame.decode("utf-8", errors="replace")
            lines = text.split("\n")
            
            # جمع كل أسطر data: متجاورة (SSE spec)
            data_parts = []
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("data:"):
                    # إزالة البادئة "data:" ومسافة واحدة إذا وجدت
                    value = stripped[5:]
                    if value.startswith(" "):
                        value = value[1:]
                    data_parts.append(value)
            
            # إذا لم يوجد حقل data: صريح، نعتبر الإطار كاملاً كبيانات
            full_data = "\n".join(data_parts) if data_parts else text
            
            if not self.auto_json:
                return full_data

            # محاولة تحليل JSON تلقائيًا
            try:
                return json.loads(full_data)
            except json.JSONDecodeError:
                # فallback: إرجاع النص الخام إذا لم يكن JSON صالحًا
                return full_data
                
        except Exception as e:
            raise PresentationError(f"SSE frame parsing failed: {e}") from e
