"""
Task queries for presentation layer.
"""
from .base import BaseQueries


class TaskQueries(BaseQueries):
    def get_pending_tasks(self) -> dict:
        """Get all file stubs as implementation tasks."""
        stubs = [
            {
                "id": f"Task_Impl_{n['id']}",
                "node_type": "task_implement",
                "target_structural_id": n["id"],
                "target_path": n.get("path", ""),
                "status": "not_started",
                "required_concerns": [c.strip() for c in n.get("required_concerns", "").split(",") if c.strip()]
            }
            for n in self.taxonomy_nodes.values()
            if n.get("node_type") == "file_stub"
        ]

        return {
            "data": stubs,
            "metadata": {
                "timestamp": self._timestamp(),
                "query_type": "pending_tasks",
                "total_count": len(stubs)
            }
        }

    def get_tasks_by_priority(self, priority: str) -> dict:
        """Get tasks filtered by priority."""
        concerns = {n["id"]: n for n in self.taxonomy_nodes.values() if n.get("node_type") == "concern"}

        stubs = [
            {
                "id": f"Task_Impl_{n['id']}",
                "node_type": "task_implement",
                "target_structural_id": n["id"],
                "target_path": n.get("path", ""),
                "status": "not_started",
                "required_concerns": [c.strip() for c in n.get("required_concerns", "").split(",") if c.strip()],
                "priority": self._derive_priority([c.strip() for c in n.get("required_concerns", "").split(",") if c.strip()], concerns)
            }
            for n in self.taxonomy_nodes.values()
            if n.get("node_type") == "file_stub"
        ]

        filtered = [s for s in stubs if s["priority"].lower() == priority.lower()]

        return {
            "data": filtered,
            "metadata": {
                "timestamp": self._timestamp(),
                "query_type": "tasks_by_priority",
                "priority": priority,
                "total_count": len(filtered)
            }
        }