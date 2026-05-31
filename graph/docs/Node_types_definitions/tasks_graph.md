# Tasks Graph - Implementation Work Items

## Overview

The **Tasks Graph** manages work items for implementing stubs and fixing issues. Unlike structural and concerns graphs, tasks are ephemeral - they can be created, completed, and removed without affecting the canonical structure.

## Node Types

### task_implement

Work item for creating a new implementation.

```json
{
  "id": "string",           // e.g., "Task_Create_WRR", "Task_Impl_Logger"
  "node_type": "task_implement",
  "target_structural_id": "string",  // References file_stub.id
  "target_path": "string",           // Expected filesystem path
  "priority": "enum",                // "low" | "medium" | "high" | "critical"
  "status": "enum",                  // "not_started" | "in_progress" | "completed" | "blocked"
  "effort_estimate": "string",       // e.g., "1d", "3d", "1w"
  "required_concerns": ["string"],     // Concern IDs this task addresses
  "created_at": "ISO datetime",
  "updated_at": "ISO datetime"
}
```

### task_debug

Work item for debugging existing code.

```json
{
  "id": "string",
  "node_type": "task_debug",
  "target_structural_id": "string",    // References file.id or module
  "bug_type": "string",              // From buggy_components
  "proposed_fix": "string",
  "severity": "enum",                // "critical" | "high" | "medium" | "low"
  "status": "enum",                  // "not_started" | "in_progress" | "completed" | "blocked"
  "requires_tasks": ["string"],       // Other task IDs that must complete first
  "created_at": "ISO datetime"
}
```

## Relationship Model

| Relationship Type | Source → Target | Description |
|-------------------|----------------|-------------|
| `targets` | task → file_stub | Task is to implement this stub |
| `fixes` | task_debug → file | Task debugs this file |
| `requires` | task → task | Task depends on another task |
| `addresses` | task → concern | Task addresses this concern |

## GraphViz DOT Representation

```dot
digraph TasksGraph {
    rankdir=TB;
    node [shape=box];
    
    // Task nodes
    "Task_Create_WRR" [label="Create WeightedRoundRobin\n[priority: medium, status: not_started]", fillcolor="#3b82f6", fontcolor=white];
    "Task_Create_Logger" [label="Create security_logger.py\n[priority: high, status: not_started]", fillcolor="#3b82f6", fontcolor=white];
    "Task_Fix_Import" [label="Fix wiring import bug\n[priority: critical, status: in_progress]", fillcolor="#ef4444", fontcolor=white];
    
    // Target stubs (structural - shown as external)
    "0.1.2.4.f" [label="weighted_round_robin.py (stub)", style=dashed, fillcolor="#e5e7eb"];
    "L1.2.5.1.f" [label="security_logger.py (stub)", style=dashed, fillcolor="#e5e7eb"];
    
    // Target files (structural)
    "0.6.1.1.f" [label="fabric_health.py", shape=note];
    
    // Edges
    "Task_Create_WRR" -> "0.1.2.4.f" [label="targets"];
    "Task_Create_Logger" -> "L1.2.5.1.f" [label="targets"];
    "Task_Fix_Import" -> "0.6.1.1.f" [label="fixes"];
    
    // Task dependency
    "Task_Create_Logger" -> "Task_Create_WRR" [label="requires", style=dotted];
}
```

## Mermaid Diagram

```mermaid
graph TD
    subgraph TASKS["Work Items"]
        Task_Create_WRR["Task_Create_WRR\n[status: not_started]"]
        Task_Create_Logger["Task_Create_Logger\n[status: not_started]"]
        Task_Fix_Import["Task_Fix_Import\n[status: in_progress]"]
    end
    
    subgraph STUBS["Target Stubs\n(external)"]
        0_1_2_4_f["weighted_round_robin.py\n(stub)"]
        L1_2_5_1_f["security_logger.py\n(stub)"]
    end
    
    Task_Create_WRR --> 0_1_2_4_f
    Task_Create_Logger --> L1_2_5_1_f
    
    classDef task fill:#3b82f6,color:white;
    classDef task_active fill:#ef4444,color:white;
    classDef stub fill:#e5e7eb,stroke-dasharray: 5 5;
```

## Core Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `status_filter()` | `(status) -> list` | Get tasks with given status |
| `priority_queue()` | `() -> list` | Get tasks sorted by priority |
| `dependency_tracking()` | `(task_id) -> list` | Get task dependencies |
| `create_task()` | `(file_stub_id, priority) -> task_id` | Create new implementation task |
| `complete_task()` | `(task_id) -> bool` | Mark task complete, promote stub to file |
| `blocked_tasks()` | `() -> list` | Get tasks blocked by dependencies |