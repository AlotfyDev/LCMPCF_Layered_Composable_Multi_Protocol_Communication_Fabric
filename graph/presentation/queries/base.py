"""
Base queries providing common utilities for all query types.
"""
from datetime import datetime


class BaseQueries:
    def __init__(self, graph):
        self.graph = graph
        self.taxonomy_nodes = getattr(graph, 'taxonomy_nodes', {})
        self.taxonomy_edges = getattr(graph, 'taxonomy_edges', {})

    def _clean_node(self, node: dict) -> dict:
        """Clean node for presentation (remove internal fields)."""
        result = {k: v for k, v in node.items() if not k.startswith("_")}
        return result

    def _timestamp(self) -> str:
        """Get current ISO-8601 timestamp."""
        return datetime.now().isoformat()

    def _derive_priority(self, concern_ids: list, concerns_lookup: dict) -> str:
        """Derive priority from highest concern severity."""
        priority_order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        max_priority = "low"

        for cid in concern_ids:
            concern = concerns_lookup.get(cid, {})
            sev = concern.get("severity", "low").lower()
            if priority_order.get(sev, 0) > priority_order.get(max_priority, 0):
                max_priority = sev

        return max_priority