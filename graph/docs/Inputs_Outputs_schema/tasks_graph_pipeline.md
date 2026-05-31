# Tasks Graph Processing Pipeline

## Overview

The tasks graph manages work items derived from both stub files (implementation tasks) and buggy components (debug tasks). Tasks are ephemeral - they can be created, completed, and removed without affecting the permanent structural taxonomy.

## Processing Steps

### Step 1: Load File Stubs for Task Creation

**Input**: Structural taxonomy `file_stub` nodes
```json
{
  "0.1.2.4.f": {
    "id": "0.1.2.4.f",
    "name": "weighted_round_robin.py",
    "node_type": "file_stub",
    "required_concerns": "NET-005"
  },
  "L1.2.5.1.f": {
    "id": "L1.2.5.1.f",
    "name": "security_logger.py", 
    "node_type": "file_stub",
    "required_concerns": "SEC-006"
  }
}
```

**Processing**:
- Filter nodes with `node_type == "file_stub"`
- Create `task_implement` nodes for each stub

**Output**: Task creation candidates
```json
[
  {
    "id": "Task_Impl_0.1.2.4.f",
    "node_type": "task_implement",
    "target_structural_id": "0.1.2.4.f",
    "target_path": "network/algorithms/weighted_round_robin.py",
    "priority": "medium",  // Derived from required_concern severity
    "status": "not_started",
    "required_concerns": ["NET-005"]
  }
]
```

---

### Step 2: Load Buggy Components for Debug Tasks

**Input**: `buggy_components/*.csv`
```csv
(buggy_components/testing_buggy_components.csv)
id,component,bug_type,severity,title,description,proposed_fix,evidence
TST-BG-001,test_live_protocol_switch.py,ImportError,critical,Malformed import chain,"ImportError in 6 places...",fix the imports,conftest.py line 14

(buggy_components/security_buggy_components.csv)  
SEC-BG-001,protocol_provider.py,logic_error,high,Endpoint used as shared_secret,"endpoint field used as secret...",Add proper shared_secret field,protocol_provider.py:78
```

**Processing**:
- Parse buggy component CSVs
- Create `task_debug` nodes for each bug report

**Output**: Debug task objects
```json
[
  {
    "id": "Task_Debug_TST-BG-001",
    "node_type": "task_debug",
    "target_structural_id": "TST-012.f",  // Maps to test file
    "bug_type": "ImportError",
    "severity": "critical",
    "status": "not_started",
    "proposed_fix": "fix the imports",
    "evidence": "conftest.py line 14"
  }
]
```

---

### Step 3: Derive Priority from Concerns

**Input**: Task nodes with `required_concerns` references

**Processing**:
- Look up concern severity for each referenced concern
- Map to task priority: critical→critical, high→high, medium→medium, low→low
- If multiple concerns, use highest severity

**Priority Mapping**:
```python
severity_to_priority = {
    "critical": "critical",
    "high": "high", 
    "medium": "medium",
    "low": "low"
}
```

**Output**: Tasks with calculated priorities
```json
{
  "Task_Impl_0.1.2.4.f": {
    "priority": "medium",  // NET-005 has medium severity
    "required_concerns": ["NET-005"]
  },
  "Task_Impl_L1.2.5.1.f": {
    "priority": "medium",  // SEC-006 has medium severity
    "required_concerns": ["SEC-006"]
  }
}
```

---

### Step 4: Create Task Dependencies

**Input**:
- Task nodes
- Concern dependencies (from concerns graph)
- Structural node relationships

**Processing**:
- If concern A depends on concern B, and both have tasks:
  - Task for A depends on Task for B (indirectly)
- Direct file dependencies become task dependencies

**Example**:
```python
# OBS-002 depends on OBS-001
# Both have stubs that need implementation
# => Task_Impl_OBS-002 depends on Task_Impl_OBS-001
```

**Output**: Task dependency edges
```json
{
  "edges": {
    "Task_Impl_OBS-002": {"Task_Impl_OBS-001"},
    "Task_Impl_NET-005": {}  // No dependencies
  }
}
```

---

### Step 5: Build Task Status Index

**Input**: Task nodes with status field

**Processing**:
- Group tasks by status
- Calculate progress metrics

**Output**: Status summary
```json
{
  "status_counts": {
    "not_started": 43,
    "in_progress": 0,
    "completed": 0,
    "blocked": 0
  },
  "status_by_priority": {
    "critical": {"not_started": 5, "in_progress": 0, "completed": 0},
    "high": {"not_started": 15, "in_progress": 0, "completed": 0}
  }
}
```

---

### Step 6: Task Completion Handler

**Input**: Completed task with `target_structural_id`

**Processing**:
- Validate task status changed to "completed"
- Get structural node (file_stub)
- Update structural node:
  - `node_type`: "file_stub" → "file"
  - `classification`: "To_Be_Implemented" → "Exists"
  - `development_state`: "not_started" → "implemented"
- Remove task from task graph
- Run dependency registration on the newly implemented file

**Output**: Updated taxonomy (persistent change)
```json
// Before: file_stub in structural taxonomy
{
  "id": "0.1.2.4.f",
  "node_type": "file_stub"
}

// After: promoted to file
{
  "id": "0.1.2.4.f", 
  "node_type": "file",
  "classification": "Exists",
  "development_state": "implemented"
}
```

## Error Handling

| Stage | Error Type | Action |
|-------|------------|--------|
| Create tasks | Missing concern | Use default priority, log warning |
| Priority derivation | Unknown severity | Default to "medium" |
| Task completion | No structural target | Log orphaned task, skip |
| Task completion | File already exists | Merge metadata, skip re-registration |
| Dependency scan | Circular dependencies | Report cycle, block completion |