# session/__init__.py
"""
OSI Layer 5 Session Management & Orchestration.
واجهة عامة موحدة لإدارة حوارات التطبيق (Dialogues)، نقاط التفتيش (Checkpoints)،
والأوركستريشن بين الجلسات وقنوات النقل (L3/L4).

✅ Core Logic: SessionCoordinator, SessionFactory
✅ Contracts: ISessionLifecycle, ICheckpointSync
✅ Orchestration (New): SessionRegistry, SessionDispatcher
✅ Resilience: Retry Hooks
"""
from __future__ import annotations

# 🧠 Core Session Logic & Factory
from session.coordinator import SessionCoordinator
from session.factory import SessionFactory

# 📜 Contracts & Interfaces
from session.ISessionLifecycle import ISessionLifecycle
from session.ICheckpointSync import ICheckpointSync

# 🔄 Orchestration & Registry (The new 3-tier structure)
from session.session_registry import SessionRegistry
from session.session_dispatcher import SessionDispatcher

# 🛡️ Hooks (Resilience Policies)
# يتم تصدير الوحدة لتمكين استيراد الخطافات المخصصة (مثل CheckpointRestoreHook)
from session.hooks import retry_hooks

__all__ = [
    # 🧠 Core Logic
    "SessionCoordinator",
    "SessionFactory",
    
    # 📜 Contracts
    "ISessionLifecycle",
    "ICheckpointSync",
    
    # 🔄 Orchestration (L3-L5 Bridge)
    "SessionRegistry",
    "SessionDispatcher",
    
    # 🛡️ Hooks Module
    "retry_hooks",
]