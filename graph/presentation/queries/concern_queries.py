"""
Concern queries for presentation layer.
"""
from .base import BaseQueries


class ConcernQueries(BaseQueries):
    def get_concerns_by_domain(self, domain: str = None) -> dict:
        """Get concerns filtered by domain."""
        concerns = [
            self._clean_node(n) for n in self.taxonomy_nodes.values()
            if n.get("node_type") == "concern"
        ]

        if domain:
            concerns = [c for c in concerns if c.get("domain") == domain]

        total = len([n for n in self.taxonomy_nodes.values()
                     if n.get("node_type") == "concern"
                     and (not domain or n.get("domain") == domain)])

        return {
            "data": concerns,
            "metadata": {
                "timestamp": self._timestamp(),
                "query_type": "concerns_by_domain",
                "domain": domain,
                "total_count": total
            }
        }

    def get_concerns_by_severity(self, severity: str) -> dict:
        """Get concerns filtered by severity."""
        concerns = [
            self._clean_node(n) for n in self.taxonomy_nodes.values()
            if n.get("node_type") == "concern" and n.get("severity", "").lower() == severity.lower()
        ]

        return {
            "data": concerns,
            "metadata": {
                "timestamp": self._timestamp(),
                "query_type": "concerns_by_severity",
                "severity": severity
            }
        }

    def get_top_concerns(self, limit: int = 10) -> dict:
        """Get top concerns by severity priority."""
        priority_order = {"critical": 4, "high": 3, "medium": 2, "low": 1}

        concerns = [
            self._clean_node(n) for n in self.taxonomy_nodes.values()
            if n.get("node_type") == "concern"
        ]

        concerns.sort(key=lambda c: priority_order.get(c.get("severity", "").lower(), 0), reverse=True)

        return {
            "data": concerns[:limit],
            "metadata": {
                "timestamp": self._timestamp(),
                "query_type": "top_concerns",
                "limit": limit,
                "total_available": len(concerns)
            }
        }