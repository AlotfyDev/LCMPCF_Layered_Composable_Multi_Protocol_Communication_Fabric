"""
Dependency queries for presentation layer.
"""
from .base import BaseQueries


class DependencyQueries(BaseQueries):
    def get_dependency_tree(self, file_id: str, depth: int = 3) -> dict:
        """Get transitive dependencies of a file."""
        result = self.graph.impact_analysis(file_id, depth) if hasattr(self.graph, 'impact_analysis') else {}

        return {
            "data": result,
            "metadata": {
                "timestamp": self._timestamp(),
                "query_type": "dependency_tree",
                "file_id": file_id,
                "depth": depth
            }
        }

    def get_cycles(self) -> dict:
        """Get all dependency cycles."""
        # Get from taxonomy_edges (populated by register_taxonomy_dependencies)
        edges = getattr(self.graph, 'taxonomy_edges', {})
        nodes = getattr(self.graph, 'taxonomy_nodes', {})

        # Filter to only file nodes
        file_nodes = {nid: n for nid, n in nodes.items() if n.get("node_type") == "file"}

        cycles = []
        # Use the original graph's detect_cycles for the main graph
        if hasattr(self.graph, 'detect_cycles'):
            cycles = self.graph.detect_cycles()

        return {
            "data": cycles,
            "metadata": {
                "timestamp": self._timestamp(),
                "query_type": "cycles",
                "cycle_count": len(cycles)
            }
        }

    def get_topological_order(self) -> dict:
        """Get files in build/dependency order using taxonomy edges."""
        # Get from taxonomy_edges (populated by register_taxonomy_dependencies)
        edges = getattr(self.graph, 'taxonomy_edges', {})
        nodes = getattr(self.graph, 'taxonomy_nodes', {})

        # Filter to only file nodes with depends_on
        file_nodes = {nid: n for nid, n in nodes.items() if n.get("node_type") == "file"}

        # Build adjacency from depends_on
        import_edges = {}
        for tax_id, node in file_nodes.items():
            depends_on = node.get("depends_on", [])
            if depends_on:
                import_edges[tax_id] = depends_on

        # Use the dependency_parser topological sort
        from graph.parsers.dependency_parser import topological_sort
        order = topological_sort(nodes, import_edges) if import_edges else []

        return {
            "data": order,
            "metadata": {
                "timestamp": self._timestamp(),
                "query_type": "topological_order",
                "total_count": len([o for o in order if isinstance(o, str)])
            }
        }