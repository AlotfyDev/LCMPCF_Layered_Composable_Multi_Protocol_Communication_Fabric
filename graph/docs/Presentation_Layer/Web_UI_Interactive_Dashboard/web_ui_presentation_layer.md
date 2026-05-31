# Web UI Interactive Dashboard - Presentation Layer

## Overview

The Web UI presentation layer consumes the unified presentation business logic layer for interactive dashboard interfaces. It focuses on structured data delivery optimized for React/Vue frontend consumption.

## Architecture

```
┌────────────────────────────────────────────────────────────┐
│         Web Interactive Dashboard                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │ React/Vue UI │  │ Live Updates │  │ Interactive  │    │
│  │ Components   │  │ (WebSocket)  │  │ Queries      │    │
│  └──────────────┘  └──────────────┘  └──────────────┘    │
└──────────────────────▲───────────────────────────────────┘
                       │ API Calls (REST/GraphQL)
┌──────────────────────┴───────────────────────────────────┐
│  Presentation Business Logic Layer                        │
│  - GraphPresenter queries                               │
│  - Data serialization                                   │
│  - State management                                     │
│  - WebSocket streaming (optional)                       │
└──────────────────────────────────────────────────────────┘
```

## API Endpoints

### REST API Structure

```
GET /api/taxonomy/summary
GET /api/taxonomy/nodes?type=file&limit=100
GET /api/taxonomy/nodes/{node_id}
GET /api/taxonomy/nodes/{node_id}/dependencies?depth=3
GET /api/taxonomy/nodes/{node_id}/dependents?depth=3

GET /api/concerns?domain=security&severity=critical
GET /api/concerns/{concern_id}
GET /api/concerns/{concern_id}/targets

GET /api/dependencies/cycles
GET /api/dependencies/order
GET /api/dependencies/impact/{file_id}

GET /api/tasks?status=not_started&priority=high
GET /api/tasks/{stub_id}
```

## Data Contracts

### Taxonomy Node Response

```typescript
interface TaxonomyNode {
  id: string;
  name: string;
  node_type: 'folder_domain' | 'folder_subdomain' | 'file' | 'file_stub' | 'concern';
  parent?: string;
  depth: number;
  depth_chain: string[];
  ancestors_chain: string[];
  
  // For files
  path?: string;
  classification?: string;
  development_state?: string;
  architectural_state?: string;
  required_concerns?: string;
  depends_on?: string[];
  depended_by?: string[];
  
  // For concerns
  domain?: string;
  category?: string;
  title?: string;
  description?: string;
  severity?: string;
  status?: string;
}
```

### Concern with Targets Response

```typescript
interface ConcernWithTargets extends TaxonomyNode {
  affects_structural: string[];  // IDs of files this concern affects
  target_details: TaxonomyNode[];  // Expanded target info
}
```

### Task Response

```typescript
interface TaskNode {
  id: string;  // e.g., "Task_Impl_0.1.2.4.f"
  node_type: 'task_implement' | 'task_debug';
  target_structural_id: string;
  target_path: string;
  priority: 'critical' | 'high' | 'medium' | 'low';
  status: 'not_started' | 'in_progress' | 'completed' | 'blocked';
  effort_estimate: 'XS' | 'S' | 'M' | 'L' | 'XL' | 'XXL';
  required_concerns: string[];
  target_details?: TaxonomyNode;  // Expanded
}
```

## Query Parameters

### Standard Filtering

| Parameter | Type | Description |
|-----------|------|-------------|
| `type` | string | Filter by node_type |
| `domain` | string | Filter by domain |
| `severity` | string | Filter by severity |
| `status` | string | Filter by task status |
| `priority` | string | Filter by priority |
| `limit` | int | Limit results |
| `offset` | int | Pagination offset |

### Depth Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `depth` | int | Transitive depth for dependency queries |
| `include_paths` | bool | Include file paths in response |

## Frontend Integration Points

### React Query Hooks

```typescript
// hooks/useTaxonomy.ts
export function useTaxonomySummary() {
  return useQuery({
    queryKey: ['taxonomy', 'summary'],
    queryFn: () => api.get('/api/taxonomy/summary')
  });
}

export function useNodeDetail(nodeId: string) {
  return useQuery({
    queryKey: ['node', nodeId],
    queryFn: () => api.get(`/api/taxonomy/nodes/${nodeId}`)
  });
}

export function useConcerns(filters: ConcernFilters) {
  return useQuery({
    queryKey: ['concerns', filters],
    queryFn: () => api.get('/api/concerns', { params: filters })
  });
}
```

### WebSocket Streaming

```python
# For live updates during builds
from fastapi import WebSocket

class PresentationStream:
    async def stream_taxonomy_updates(self, websocket: WebSocket):
        """Stream taxonomy changes in real-time."""
        async for change in graph.change_stream():
            await websocket.send_json({
                "type": "taxonomy_update",
                "node_id": change.node_id,
                "change": change.type
            })
```

## Interactive Features

### Dependency Explorer

```json
{
    "endpoint": "/api/taxonomy/nodes/{file_id}/explorer",
    "params": {
        "direction": "imports|imported_by|both",
        "depth": 3,
        "exclude_external": true
    },
    "response": {
        "node": TaxonomyNode,
        "dependencies": [{
            "id": "0.1.2.f",
            "path": "network/protocol.py",
            "level": 1,
            "type": "direct|transitive"
        }],
        "dependents": [...]
    }
}
```

### Concern Impact Visualization

```json
{
    "endpoint": "/api/concerns/{concern_id}/impact",
    "response": {
        "concern": ConcernNode,
        "affected_files": [TaxonomyNode, ...],
        "dependency_impact": {
            "file_id": {
                "transitive_dependents": 15,
                "impact_score": 8.5
            }
        }
    }
}
```

### Task Prioritization View

```json
{
    "endpoint": "/api/tasks/priority-matrix",
    "response": {
        "matrix": {
            "critical_not_started": [...],
            "high_not_started": [...],
            "high_in_progress": [...]
        },
        "stats": {
            "total_tasks": 43,
            "blocked_by_cycles": 2
        }
    }
}
```

## Presentation Layer State

The web UI maintains client-side state derived from presentation queries:

```typescript
interface PresentationState {
  selectedNode: string | null;
  activeFilters: Record<string, any>;
  currentView: 'taxonomy' | 'concerns' | 'dependencies' | 'tasks';
  expandedChains: Record<string, boolean>;
  searchQuery: string;
}
```

## Design Constraints

1. **API Contract Stability**: Response format must be stable for frontend caching
2. **Pagination Required**: Large datasets must support limit/offset
3. **Error Consistency**: All errors follow `{"error": string, "code": int}` format
4. **WebSocket Backoff**: Implement exponential backoff for reconnections

## Related Documentation

- `presentation_logic_unified_base_back_layer.md`
- `CLI/cli_presentation_layer.md`