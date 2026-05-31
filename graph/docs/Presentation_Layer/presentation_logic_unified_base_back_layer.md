# Presentation Logic - Unified Base Back Layer

## Overview

The unified presentation business logic layer provides clean abstraction between core graph operations and presentation endpoints. Uses separated query modules following single-responsibility principle.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Presentation Endpoints                        │
│  ┌───────────────┐         ┌──────────────────────────────┐       │
│  │ CLI Interface │         │ Web UI Interactive Dashboard │       │
│  └───────────────┘         └──────────────────────────────┘       │
└──────────▲─────────────────────────────▲──────────────────────────┘
           │                             │
           └───────────────────────────────┘
                            │
                ┌───────────────────────┐
                │ Presentation Business │
                │     Logic Layer       │  ← THIS DOCUMENT
                └──────────▲────────────┘
                           │
                ┌───────────────────────┐
                │    Graph Core         │
                │ (Graph, Taxonomies,   │
                │  Dependencies)        │
                └───────────────────────┘
```

## Core Principles

1. **Isolation**: Presentation layers never access Graph nodes/edges directly
2. **Read-Only Queries**: All operations are queries - no mutations through presentation API
3. **Unified Format**: Common output format regardless of endpoint
4. **Stateless**: Each query is independent, no session state

## API Interface

### 1. Taxonomy Queries (delegates to `TaxonomyQueries`)

```python
# presentation/queries/taxonomy_queries.py
class TaxonomyQueries(BaseQueries):
    def get_taxonomy_summary(self) -> dict:
        return self.graph.taxonomy_summary()

    def get_nodes_by_type(self, node_type: str, limit: int = None, offset: int = 0) -> dict:
        # Filter and paginate nodes
        ...

    def get_node_detail(self, node_id: str) -> dict:
        # Get single node with cleaned output
        ...
```

### 2. Concern Queries (delegates to `ConcernQueries`)

```python
# presentation/queries/concern_queries.py
class ConcernQueries(BaseQueries):
    def get_concerns_by_domain(self, domain: str = None) -> dict: ...
    def get_concerns_by_severity(self, severity: str) -> dict: ...
    def get_top_concerns(self, limit: int = 10) -> dict: ...
```

### 3. Dependency Queries (delegates to `DependencyQueries`)

```python
# presentation/queries/dependency_queries.py
class DependencyQueries(BaseQueries):
    def get_dependency_tree(self, file_id: str, depth: int = 3) -> dict: ...
    def get_cycles(self) -> dict: ...
    def get_topological_order(self) -> dict: ...
```

### 4. Task Queries (delegates to `TaskQueries`)

```python
# presentation/queries/task_queries.py
class TaskQueries(BaseQueries):
    def get_pending_tasks(self) -> dict: ...
    def get_tasks_by_priority(self, priority: str) -> dict: ...
```

## Output Format Standards

All queries return a standardized format:

```json
{
    "data": [...],        // Query results
    "metadata": {         // Query metadata
        "timestamp": "ISO-8601",
        "query_type": "string",
        "record_count": int,
        "filters_applied": {}
    },
    "summary": {          // Optional summary stats
        "total": int,
        "by_type": {},
        "by_severity": {}
    }
}
```

## Cross-Cutting Concern Integration

The presentation layer handles concern presentation uniformly:

| Concern Domain | Presentation Category |
|----------------|---------------------|
| security | 🔒 Security Issues |
| observability | 📊 Observability Gaps |
| testing | 🧪 Testing Deficits |
| devops | 🐳 DevOps Infrastructure |
| wiring_di | 🔌 Wiring & DI |
| gateway_sdk | 🌐 Gateway SDK |

## Error Handling

```python
class PresentationError(Exception):
    """Base presentation error."""

def safe_query(self, query_func, *args, **kwargs) -> dict:
    """Wrap query functions with error handling."""
    try:
        result = query_func(*args, **kwargs)
        return {"status": "success", "data": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}
```

## Integration Points

### For CLI Layer
- Direct method calls with text output
- Uses `json.dumps(result, indent=2)` for structured output
- Minimal formatting, maximum data

### For Web UI Layer
- Same method calls with potential for streaming
- Optional filtering/sorting parameters
- Designed for React/Vue consumption

## File Location

`graph/presentation/presenter.py` - Implements the `GraphPresenter` class

---

## Related Documentation

- `CLI/cli_presentation_layer.md`
- `Web_UI_Interactive_Dashboard/web_ui_presentation_layer.md`

---

## File Structure

```
graph/presentation/
├── __init__.py           # Exports GraphPresenter
├── presenter.py          # Unified presenter delegating to queries
├── queries/
│   ├── __init__.py       # Exports all query classes
│   ├── base.py           # BaseQueries with shared utilities
│   ├── taxonomy_queries.py
│   ├── concern_queries.py
│   ├── dependency_queries.py
│   └── task_queries.py
└── formatters/
    ├── __init__.py       # Exports all formatters
    ├── taxonomy_formatter.py
    ├── concern_formatter.py
    └── task_formatter.py
```