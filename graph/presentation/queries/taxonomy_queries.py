"""
Taxonomy queries for presentation layer.
"""
from ..queries.base import BaseQueries


class TaxonomyQueries(BaseQueries):
    def get_taxonomy_summary(self) -> dict:
        """Get high-level taxonomy statistics."""
        result = self.graph.taxonomy_summary()
        return {
            "data": result,
            "metadata": {
                "timestamp": self._timestamp(),
                "query_type": "taxonomy_summary",
                "record_count": result.get("total_nodes", 0)
            }
        }

    def get_nodes_by_type(self, node_type: str, limit: int = None, offset: int = 0) -> dict:
        """Get all nodes of a specific type."""
        nodes = self.taxonomy_nodes
        filtered = [
            self._clean_node(n) for n in nodes.values()
            if n.get("node_type") == node_type
        ]

        if limit:
            filtered = filtered[offset:offset + limit]

        total = len([n for n in nodes.values() if n.get("node_type") == node_type])
        return {
            "data": filtered,
            "metadata": {
                "timestamp": self._timestamp(),
                "query_type": "nodes_by_type",
                "node_type": node_type,
                "total_count": total,
                "returned_count": len(filtered),
                "offset": offset
            }
        }

    def get_node_detail(self, node_id: str) -> dict:
        """Get detailed information about a single node."""
        node = self.taxonomy_nodes.get(node_id, {})
        return {
            "data": self._clean_node(node),
            "metadata": {
                "timestamp": self._timestamp(),
                "query_type": "node_detail",
                "node_id": node_id
            }
        }