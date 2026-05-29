# session/adapters/cli_session.py
import asyncio, uuid, time, json, os
from pathlib import Path
from typing import Optional
from session.protocol import ISessionLifecycle, ICheckpointSync
from session.protocol import SessionConfig, SessionStatus, CheckpointMeta, PrunePolicy

class CLISessionAdapter(ISessionLifecycle, ICheckpointSync):
    """محول جلسة CLI: يدير الحوار المنطقي فوق stdin/stdout مع نقاط تفتيش ملفية"""
    
    def __init__(self, workspace_dir: Optional[str] = None):
        self._sessions: dict[str, dict] = {}
        self._workspace = Path(workspace_dir or tempfile.gettempdir()) / "cli_sessions"
        self._workspace.mkdir(parents=True, exist_ok=True)

    # --- ISessionLifecycle ---
    async def open(self, config: Optional[SessionConfig] = None) -> str:
        sid = str(uuid.uuid4())
        self._sessions[sid] = {
            "status": SessionStatus.ACTIVE,
            "created_at": time.time(),
            "last_activity": time.time(),
            "config": config or SessionConfig(),
            "pid_ref": None  # يُربط لاحقًا بـ L4 عند تشغيل العملية
        }
        return sid

    async def close(self, session_id: str, reason: str = "normal") -> None:
        if session_id not in self._sessions:
            raise ValueError(f"Session {session_id} not found")
        self._sessions[session_id]["status"] = SessionStatus.CLOSED
        # تنظيف نقاط التفتيش القديمة تلقائيًا
        await self.prune(session_id, PrunePolicy(keep_last=1, max_age_seconds=60))

    async def refresh(self, session_id: str) -> bool:
        if session_id not in self._sessions:
            return False
        self._sessions[session_id]["last_activity"] = time.time()
        # التحقق من انتهاء الصلاحية
        sess = self._sessions[session_id]
        if time.time() - sess["created_at"] > sess["config"].ttl_seconds:
            sess["status"] = SessionStatus.EXPIRED
            return False
        return True

    async def status(self, session_id: str) -> SessionStatus:
        if session_id not in self._sessions:
            return SessionStatus.CLOSED
        return self._sessions[session_id]["status"]

    # --- ICheckpointSync ---
    async def mark(self, session_id: str, payload: bytes, meta: Optional[CheckpointMeta] = None) -> str:
        if session_id not in self._sessions:
            raise ValueError("Session not open")
        cid = str(uuid.uuid4())
        path = self._workspace / f"{session_id}_{cid}.ckpt"
        data = meta.model_dump() if meta else {"offset": 0, "size": len(payload)}
        with open(path, "wb") as f:
            f.write(json.dumps(data).encode() + b"\nPAYLOAD_START\n" + payload)
        return cid

    async def get_latest(self, session_id: str) -> tuple[str, bytes]:
        ckpts = list(self._workspace.glob(f"{session_id}_*.ckpt"))
        if not ckpts:
            raise FileNotFoundError("No checkpoints found")
        latest = max(ckpts, key=lambda p: p.stat().st_mtime)
        cid = latest.stem.split("_", 1)[1]
        content = latest.read_bytes()
        payload = content.split(b"\nPAYLOAD_START\n", 1)[1]
        return cid, payload

    async def restore(self, session_id: str, checkpoint_id: str) -> bytes:
        _, payload = await self.get_latest(session_id)  # تبسيط للعرض
        return payload

    async def prune(self, session_id: str, policy: PrunePolicy) -> int:
        ckpts = sorted(self._workspace.glob(f"{session_id}_*.ckpt"), key=lambda p: p.stat().st_mtime)
        to_remove = ckpts[:-policy.keep_last] if len(ckpts) > policy.keep_last else []
        count = 0
        for p in to_remove:
            if time.time() - p.stat().st_mtime > policy.max_age_seconds:
                p.unlink()
                count += 1
        return count

    async def list(self, session_id: str) -> list[CheckpointMeta]:
        return []  # يُنفذ بقراءة الهيدر من الملفات عند الحاجة