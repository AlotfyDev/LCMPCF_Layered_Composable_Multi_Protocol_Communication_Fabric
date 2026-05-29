# session/factory.py
from typing import Literal, Optional
from session.protocol import ISessionLifecycle, ICheckpointSync
from session.adapters.cli_session import CLISessionAdapter
from session.adapters.inprocess_session import InProcessSessionAdapter
from session.adapters.network_session import NetworkSessionAdapter, IExternalStore

class UnifiedSessionManager(ISessionLifecycle, ICheckpointSync):
    """غلاف موحد يجمع الواجهتين لتسهيل الحقن في BaseActor"""
    def __init__(self, lifecycle: ISessionLifecycle, checkpoint: ICheckpointSync):
        self.lifecycle = lifecycle
        self.checkpoint = checkpoint
    # تفويض جميع الطرق تلقائيًا
    def __getattr__(self, name):
        if hasattr(self.lifecycle, name): return getattr(self.lifecycle, name)
        return getattr(self.checkpoint, name)

class SessionFactory:
    @staticmethod
    def create(
        transport_type: Literal["cli", "inprocess", "a2a"],
        workspace_dir: Optional[str] = None,
        external_store: Optional[IExternalStore] = None,
        node_id: str = "default"
    ) -> UnifiedSessionManager:
        match transport_type:
            case "cli":
                return UnifiedSessionManager(
                    CLISessionAdapter(workspace_dir=workspace_dir),
                    CLISessionAdapter(workspace_dir=workspace_dir)
                )
            case "inprocess":
                return UnifiedSessionManager(
                    InProcessSessionAdapter(),
                    InProcessSessionAdapter()
                )
            case "a2a":
                if not external_store:
                    raise ValueError("A2A requires an external store (Redis/DB)")
                return UnifiedSessionManager(
                    NetworkSessionAdapter(external_store, node_id),
                    NetworkSessionAdapter(external_store, node_id)
                )
            case _:
                raise ValueError(f"Unsupported transport type: {transport_type}")