# transport/_ws_framing.py
"""
OSI L4 WebSocket Framing Engine (RFC 6455).
مسؤوليته حصريًا: ترميز/فك ترميز إطارات WebSocket الثنائية.
يعزل تعقيد البروتوكول عن الناقل الرئيسي. حالة صفرية (Stateless).
"""
from __future__ import annotations

import struct
import os
from typing import Tuple, Optional

# Opcodes according to RFC 6455
OP_TEXT = 0x1
OP_BINARY = 0x2
OP_CLOSE = 0x8
OP_PING = 0x9
OP_PONG = 0xA

class WSFrameError(Exception):
    """خطأ في بنية أو محتوى إطار WebSocket."""
    pass

class WSFramingEngine:
    @staticmethod
    def encode_frame(
        payload: bytes,
        opcode: int = OP_BINARY,
        fin: bool = True,
        mask: bool = True
    ) -> bytes:
        """
        يبني إطار WebSocket ثنائي كامل.
        mask=True افتراضيًا لاتجاه OUTBOUND (Client -> Server حسب RFC)
        """
        # البايت الأول: FIN + RSV(0) + Opcode
        frame = bytearray()
        frame.append((0x80 if fin else 0x00) | (opcode & 0x0F))
        
        # البايت الثاني: MASK + Payload Length
        length = len(payload)
        if length <= 125:
            frame.append((0x80 if mask else 0x00) | length)
        elif length <= 65535:
            frame.append((0x80 if mask else 0x00) | 126)
            frame.extend(struct.pack(">H", length))
        else:
            frame.append((0x80 if mask else 0x00) | 127)
            frame.extend(struct.pack(">Q", length))
            
        # مفتاح التمويه (Masking Key) 4 بايتات
        if mask:
            mask_key = os.urandom(4)
            frame.extend(mask_key)
            # تطبيق XOR على الحمولة
            masked_payload = bytearray(len(payload))
            for i in range(len(payload)):
                masked_payload[i] = payload[i] ^ mask_key[i % 4]
            frame.extend(masked_payload)
        else:
            frame.extend(payload)
            
        return bytes(frame)

    @staticmethod
    def parse_header(header_bytes: bytes) -> Tuple[int, int, int, int]:
        """
        يحلل أول بايتين + الأطوال الممتدة ومفتاح التمويه.
        يعيد: (fin_rsv_opcode, mask_bit, payload_len, header_total_size)
        """
        if len(header_bytes) < 2:
            raise WSFrameError("Incomplete frame header")
            
        fin_rsv_opcode = header_bytes[0]
        mask_len_byte = header_bytes[1]
        mask = (mask_len_byte >> 7) & 1
        payload_len = mask_len_byte & 0x7F
        header_size = 2
        
        if payload_len == 126:
            if len(header_bytes) < 4:
                raise WSFrameError("Missing 16-bit length extension")
            payload_len = struct.unpack(">H", header_bytes[2:4])[0]
            header_size = 4
        elif payload_len == 127:
            if len(header_bytes) < 10:
                raise WSFrameError("Missing 64-bit length extension")
            payload_len = struct.unpack(">Q", header_bytes[2:10])[0]
            header_size = 10
            
        return fin_rsv_opcode, mask, payload_len, header_size

    @staticmethod
    def unmask_payload(payload: bytes, mask_key: bytes) -> bytes:
        """يفك تمويه الحمولة (Server -> Client عادة لا تحتاج تمويه)"""
        if not mask_key or len(mask_key) != 4:
            return payload
        return bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))