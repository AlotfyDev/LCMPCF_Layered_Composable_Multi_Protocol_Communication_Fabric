"""
GraphPresenter - Unified Presentation Business Logic

Delegates to specialized query classes, separates concerns by query type.
"""
from .queries import TaxonomyQueries, ConcernQueries, DependencyQueries, TaskQueries


class GraphPresenter:
    """
    Unified presenter that delegates to specialized query handlers.
    """

    def __init__(self, graph):
        self.graph = graph

        # Delegate to specialized query classes
        self.taxonomy = TaxonomyQueries(graph)
        self.concerns = ConcernQueries(graph)
        self.dependencies = DependencyQueries(graph)
        self.tasks = TaskQueries(graph)

    # Taxonomy delegation
    def get_taxonomy_summary(self) -> dict:
        return self.taxonomy.get_taxonomy_summary()

    def get_nodes_by_type(self, node_type: str, limit: int = None, offset: int = 0) -> dict:
        return self.taxonomy.get_nodes_by_type(node_type, limit, offset)

    def get_node_detail(self, node_id: str) -> dict:
        return self.taxonomy.get_node_detail(node_id)

    # Concern delegation
    def get_concerns_by_domain(self, domain: str = None) -> dict:
        return self.concerns.get_concerns_by_domain(domain)

    def get_concerns_by_severity(self, severity: str) -> dict:
        return self.concerns.get_concerns_by_severity(severity)

    def get_top_concerns(self, limit: int = 10) -> dict:
        return self.concerns.get_top_concerns(limit)

    # Dependency delegation
    def get_dependency_tree(self, file_id: str, depth: int = 3) -> dict:
        return self.dependencies.get_dependency_tree(file_id, depth)

    def get_cycles(self) -> dict:
        return self.dependencies.get_cycles()

    def get_topological_order(self) -> dict:
        return self.dependencies.get_topological_order()

    # Task delegation
    def get_pending_tasks(self) -> dict:
        return self.tasks.get_pending_tasks()

    def get_tasks_by_priority(self, priority: str) -> dict:
        return self.tasks.get_tasks_by_priority(priority)