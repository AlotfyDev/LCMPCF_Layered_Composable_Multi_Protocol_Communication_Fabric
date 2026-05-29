# session/adapters/network_session.py
import asyncio, uuid, time, json
from typing import Optional
from session.protocol import ISessionLifecycle, ICheckpointSync
from session.protocol import SessionConfig, SessionStatus, CheckpointMeta, PrunePolicy

# واجهة افتراضية للمخزن الخارجي (يُحقن عند التكوين)
class IExternalStore:
    async def set(self, key: str, val: str, ttl: int): ...
    async def get(self, key: str) -> Optional[str]: ...
    async def delete(self, key: str): ...
    async def list_keys(self, prefix: str) -> list[str]: ...

class NetworkSessionAdapter(ISessionLifecycle, ICheckpointSync):
    """محول جلسة A2A/Network: يدير حوارًا موزعًا مع نقاط تفتيش خارجية"""
    
    def __init__(self, store: IExternalStore, node_id: str = "local"):
        self.store = store
        self.node_id = node_id
        self._prefix = f"session:{self.node_id}"

    # --- ISessionLifecycle ---
    async def open(self, config: Optional[SessionConfig] = None) -> str:
        sid = str(uuid.uuid4())
        cfg = config or SessionConfig()
        state = {"status": SessionStatus.ACTIVE.value, "created": time.time(), "last": time.time(), "ttl": cfg.ttl_seconds}
        await self.store.set(f"{self._prefix}:{sid}:state", json.dumps(state), int(cfg.ttl_seconds))
        await self.store.set(f"{self._prefix}:{sid}:config", json.dumps(cfg.model_dump()), int(cfg.ttl_seconds))
        return sid

    async def close(self, session_id: str, reason: str = "normal") -> None:
        state = json.loads(await self.store.get(f"{self._prefix}:{session_id}:state") or "{}")
        state["status"] = SessionStatus.CLOSED.value
        await self.store.set(f"{self._prefix}:{session_id}:state", json.dumps(state), 60)

    async def refresh(self, session_id: str) -> bool:
        key = f"{self._prefix}:{session_id}:state"
        raw = await self.store.get(key)
        if not raw: return False
        state = json.loads(raw)
        state["last"] = time.time()
        await self.store.set(key, json.dumps(state), state.get("ttl", 3600))
        return True

    async def status(self, session_id: str) -> SessionStatus:
        raw = await self.store.get(f"{self._prefix}:{session_id}:state")
        return SessionStatus(json.loads(raw)["status"]) if raw else SessionStatus.CLOSED

    # --- ICheckpointSync ---
    async def mark(self, session_id: str, payload: bytes, meta: Optional[CheckpointMeta] = None) -> str:
        cid = str(uuid.uuid4())
        key = f"{self._prefix}:{session_id}:ckpt:{cid}"
        data = {"meta": (meta or CheckpointMeta(cid, time.time(), 0, len(payload))).model_dump(), "payload": payload.decode("latin1")}
        await self.store.set(key, json.dumps(data), 86400)
        # تحديث مؤشر latest
        await self.store.set(f"{self._prefix}:{session_id}:latest", cid, 3600)
        return cid

    async def get_latest(self, session_id: str) -> tuple[str, bytes]:
        cid = await self.store.get(f"{self._prefix}:{session_id}:latest")
        if not cid: raise FileNotFoundError("No checkpoints")
        raw = await self.store.get(f"{self._prefix}:{session_id}:ckpt:{cid}")
        data = json.loads(raw)
        return cid, data["payload"].encode("latin1")

    async def restore(self, session_id: str, checkpoint_id: str) -> bytes:
        _, payload = await self.get_latest(session_id)  # تبسيط
        return payload

    async def prune(self, session_id: str, policy: PrunePolicy) -> int:
        keys = await self.store.list_keys(f"{self._prefix}:{session_id}:ckpt:")
        # منطق حذف موزع يعتمد على timestamps (يُطبق حسب نوع المخزن)
        return 0  # يُنفذ فعليًا عند ربط Redis/Postgres

    async def list(self, session_id: str) -> list[CheckpointMeta]:
        keys = await self.store.list_keys(f"{self._prefix}:{session_id}:ckpt:")
        return []  # يُعبأ بقراءة البيانات الوصفية من المخزن