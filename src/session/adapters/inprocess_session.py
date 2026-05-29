# session/adapters/inprocess_session.py
import asyncio, uuid, time
from typing import Optional
from session.protocol import ISessionLifecycle, ICheckpointSync
from session.protocol import SessionConfig, SessionStatus, CheckpointMeta, PrunePolicy

class InProcessSessionAdapter(ISessionLifecycle, ICheckpointSync):
    """محول جلسة InProcess: إدارة سريعة داخل مساحة الذاكرة المشتركة"""
    
    def __init__(self):
        self._sessions: dict[str, dict] = {}
        self._checkpoints: dict[str, list[dict]] = {}
        self._lock = asyncio.Lock()

    # --- ISessionLifecycle ---
    async def open(self, config: Optional[SessionConfig] = None) -> str:
        sid = str(uuid.uuid4())
        self._sessions[sid] = {
            "status": SessionStatus.ACTIVE,
            "created_at": time.time(),
            "last_activity": time.time(),
            "config": config or SessionConfig()
        }
        self._checkpoints[sid] = []
        return sid

    async def close(self, session_id: str, reason: str = "normal") -> None:
        async with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id]["status"] = SessionStatus.CLOSED
                self._checkpoints.pop(session_id, None)

    async def refresh(self, session_id: str) -> bool:
        async with self._lock:
            if session_id not in self._sessions: return False
            self._sessions[session_id]["last_activity"] = time.time()
            return True

    async def status(self, session_id: str) -> SessionStatus:
        return self._sessions.get(session_id, {}).get("status", SessionStatus.CLOSED)

    # --- ICheckpointSync ---
    async def mark(self, session_id: str, payload: bytes, meta: Optional[CheckpointMeta] = None) -> str:
        async with self._lock:
            if session_id not in self._checkpoints:
                raise ValueError("Session not open")
            cid = str(uuid.uuid4())
            self._checkpoints[session_id].append({
                "id": cid, "payload": payload, "meta": meta or CheckpointMeta(checkpoint_id=cid, created_at=time.time(), stream_offset=0, size_bytes=len(payload)),
                "ts": time.time()
            })
            return cid

    async def get_latest(self, session_id: str) -> tuple[str, bytes]:
        async with self._lock:
            ckpts = self._checkpoints.get(session_id, [])
            if not ckpts: raise FileNotFoundError("No checkpoints")
            latest = ckpts[-1]
            return latest["id"], latest["payload"]

    async def restore(self, session_id: str, checkpoint_id: str) -> bytes:
        async with self._lock:
            for c in self._checkpoints.get(session_id, []):
                if c["id"] == checkpoint_id:
                    return c["payload"]
            raise ValueError("Checkpoint not found")

    async def prune(self, session_id: str, policy: PrunePolicy) -> int:
        async with self._lock:
            ckpts = self._checkpoints.get(session_id, [])
            if len(ckpts) <= policy.keep_last: return 0
            to_keep = ckpts[-policy.keep_last:]
            removed = [c for c in ckpts if c["id"] not in {k["id"] for k in to_keep}]
            self._checkpoints[session_id] = to_keep
            return len(removed)

    async def list(self, session_id: str) -> list[CheckpointMeta]:
        async with self._lock:
            return [c["meta"] for c in self._checkpoints.get(session_id, [])]