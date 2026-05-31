"""
Presentation queries package - Separated query implementations.
"""
from .base import BaseQueries
from .taxonomy_queries import TaxonomyQueries
from .concern_queries import ConcernQueries
from .dependency_queries import DependencyQueries
from .task_queries import TaskQueries

__all__ = ["BaseQueries", "TaxonomyQueries", "ConcernQueries", "DependencyQueries", "TaskQueries"]