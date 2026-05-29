# actors/base_actor.py
"""
Base Actor (OSI L8 Pure Business Logic).
يحتوي فقط على قواعد العمل، التحويلات، واتخاذ القرارات.
لا يعرف شيئًا عن الشبكة، البروتوكولات، الجلسات، أو البنية التحتية.
يعتمد حصريًا على عقد ICommunicationGateway عبر Dependency Injection.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, AsyncIterator, Callable, Dict, Optional

from contracts.communication_gateway import ICommunicationGateway

logger = logging.getLogger(__name__)


class BaseActor:
    """
    وكيل أعمال نقي. يدير المهام، التحويلات، والتنسيق المنطقي.
    يمكن إعادة استخدامه في نمط Embedded أو Gateway دون تعديل سطر واحد.
    """

    def __init__(
        self,
        gateway: ICommunicationGateway,
        actor_id: str = "default",
        on_event_callback: Optional[Callable[[Dict[str, Any]], Any]] = None
    ):
        self._gateway = gateway
        self.actor_id = actor_id
        self._on_event = on_event_callback
        self._active_sessions: set[str] = set()

    async def execute_task(self, payload: Dict[str, Any], protocol: str = "http") -> Dict[str, Any]:
        """ينفذ مهمة outbound مع إدارة جلسة تلقائية ومعالجة أخطاء منطقية."""
        session_id = f"{self.actor_id}-{uuid.uuid4().hex[:8]}"
        self._active_sessions.add(session_id)

        try:
            logger.info(f"[Actor:{self.actor_id}] Executing task via {protocol} (session={session_id})")
            
            # إرسال عبر الفابريك (L3-L7 مُدارة داخليًا)
            result = await self._gateway.send(
                payload=payload,
                protocol=protocol,
                session_id=session_id,
                metadata={"actor_id": self.actor_id, "priority": "high"}
            )

            # معالجة منطقية للنتيجة
            processed = self._transform_result(result)
            return {"status": "success", "data": processed, "session_id": session_id}

        except Exception as e:
            logger.error(f"[Actor:{self.actor_id}] Task failed: {e}")
            return {"status": "error", "message": str(e), "session_id": session_id}
        finally:
            # تنظيف تلقائي (يمكن تأجيله إذا كانت الجلسة طويلة الأمد)
            await self._gateway.close_session(session_id, protocol=protocol)
            self._active_sessions.discard(session_id)

    async def stream_response(self, query: str, protocol: str = "http") -> AsyncIterator[Dict[str, Any]]:
        """يتعامل مع البث المتدفق (SSE/Chunks) ويعيد كائنات تطبيقية مفككة."""
        session_id = f"{self.actor_id}-stream-{uuid.uuid4().hex[:6]}"
        self._active_sessions.add(session_id)
        
        try:
            async for chunk in self._gateway.receive_stream(
                byte_stream=self._mock_external_stream(query),
                protocol=protocol,
                session_id=session_id,
                metadata={"stream_type": "llm_output"}
            ):
                # تحويل منطقي لكل شريحة
                yield {"chunk": chunk, "actor": self.actor_id, "session": session_id}
        except Exception as e:
            logger.warning(f"[Actor:{self.actor_id}] Stream interrupted: {e}")
            yield {"error": str(e), "type": "stream_failure"}
        finally:
            await self._gateway.close_session(session_id, protocol=protocol)
            self._active_sessions.discard(session_id)

    def handle_inbound_event(self, event: Dict[str, Any]) -> None:
        """يُستدعى من Edge Adapters عند وصول حدث/رسالة واردة."""
        logger.info(f"[Actor:{self.actor_id}] Received inbound event: {event.get('type')}")
        if self._on_event:
            self._on_event(event)
        # منطق معالجة الحدث محليًا أو توجيهه لخدمات أخرى عبر self._gateway.send(...)

    async def close(self) -> None:
        """ينظف الجلسات النشطة عند إيقاف الوكيل."""
        for sid in list(self._active_sessions):
            try:
                await self._gateway.close_session(sid)
            except Exception:
                pass
        self._active_sessions.clear()
        logger.info(f"[Actor:{self.actor_id}] Closed and sessions cleaned up")

    # ── Internal Helpers ─────────────────────────────────────

    def _transform_result(self, raw: Any) -> Any:
        """تحويل منطقي خاص بالأعمال (عزل عن الفابريك)"""
        if isinstance(raw, dict):
            raw["_actor_processed"] = True
            raw["_timestamp"] = asyncio.get_event_loop().time()
        return raw

    @staticmethod
    async def _mock_external_stream(query: str) -> AsyncIterator[bytes]:
        """محاكاة تدفق خارجي للعرض فقط (في الإنتاج يأتي من الـ Fabric عبر الـ Adapter)"""
        import json
        for i in range(3):
            yield json.dumps({"step": i, "content": f"Part {i} for '{query}'"}).encode()
            await asyncio.sleep(0.1)
            
"""


"""