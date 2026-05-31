# Tasks Graph Parsers

## Overview

Parsers for creating work items from stubs (implementation tasks) and buggy components (debug tasks). Tasks represent the bridge between planned work and completed implementation.

---

## 1. Task Creation Parser (from File Stubs)

**Input Schema**: Structural taxonomy file_stub nodes
```json
{
  "id": "string",           // e.g., "0.1.2.4.f"
  "name": "string",         // e.g., "weighted_round_robin.py"
  "path": "string",         // e.g., "network/algorithms/weighted_round_robin.py"
  "node_type": "file_stub",
  "parent": "string",       // References subdomain
  "required_concerns": "string"  // e.g., "NET-005"
}
```

**Parser Logic**:
```python
# parsers/task_creation.py
def create_implementation_tasks(file_stubs: list[dict], concerns_lookup: dict) -> list[dict]:
    """
    Transform file_stub nodes into implementation tasks.
    
    Output Schema:
    [
        {
            "id": "string",  // e.g., "Task_Impl_0.1.2.4.f"
            "node_type": "task_implement",
            "target_structural_id": "string",  // Original stub ID
            "target_path": "string",
            "priority": "string",  // Derived from concern severity
            "status": "string",   // Default: "not_started"
            "effort_estimate": "XS|S|M|L|XL",  // From concern
            "required_concerns": ["string"]  // Parsed list
        }
    ]
    """
    tasks = []
    
    for stub in file_stubs:
        # Generate task ID
        task_id = f"Task_Impl_{stub['id']}"
        
        # Parse required concerns
        req_concerns = [c.strip() for c in stub.get("required_concerns", "").split(",") if c.strip()]
        
        # Derive priority from concern severity
        priority = "medium"  # default
        for cid in req_concerns:
            concern = concerns_lookup.get(cid, {})
            sev = concern.get("severity", "medium").lower()
            if sev == "critical":
                priority = "critical"
                break
            elif sev == "high":
                priority = "high"
            elif sev == "medium" and priority != "high":
                priority = "medium"
        
tasks.append({
             "id": task_id,
             "node_type": "task_implement",
             "target_structural_id": stub["id"],
             "target_path": stub.get("path", ""),
             "priority": priority,
             "status": "not_started",
             "effort_estimate": concern.get("effort_estimate", "S") if req_concerns else "S",
             "required_concerns": req_concerns
         })
    
    return tasks
```

**Output Schema**:
```json
[
  {
    "id": "Task_Impl_0.1.2.4.f",
    "node_type": "task_implement",
    "target_structural_id": "0.1.2.4.f",
    "target_path": "network/algorithms/weighted_round_robin.py",
    "priority": "medium",
    "status": "not_started",
    "effort_estimate": "M",
    "required_concerns": ["NET-005"]
  }
]
```

---

## 2. Buggy Components Parser

**Input Schema**: `buggy_components/*.csv`
```csv
id,component,bug_type,severity,title,description,proposed_fix,evidence
TST-BG-001,test_live_protocol_switch.py,ImportError,critical,Malformed import chain,"ImportError in 6 places...","fix the imports","conftest.py line 14"
SEC-BG-001,protocol_provider.py,logic_error,high,Endpoint used as shared_secret,"endpoint field used as secret...","Add separate shared_secret field","protocol_provider.py:78"
```

**Parser Logic**:
```python
# parsers/bug_parser.py
def parse_buggy_components(filepath: Path) -> list[dict]:
    """
    Parse buggy_components CSV into debug task objects.
    
    Output Schema:
    [
        {
            "id": "string",  // e.g., "Task_Debug_TST-BG-001"
            "node_type": "task_debug",
            "target_structural_id": "string",  // Resolved from component path
            "source_component_id": "string",   // Original bug ID
            "bug_type": "string",
            "severity": "string",
            "status": "not_started",
            "proposed_fix": "string",
            "evidence": "string"
        }
    ]
    """
    tasks = []
    
    with open(filepath, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            component = row.get("component", "").strip()
            
            # Try to map component to structural node
            target_id = resolve_component_to_structural(component)
            
            tasks.append({
                "id": f"Task_Debug_{row['id'].strip()}",
                "node_type": "task_debug",
                "target_structural_id": target_id,
                "source_component_id": row["id"].strip(),
                "bug_type": row.get("bug_type", "").strip(),
                "severity": row.get("severity", "").strip(),
                "status": "not_started",
                "proposed_fix": row.get("proposed_fix", "").strip(),
                "evidence": row.get("evidence", "").strip()
            })
    
    return tasks

def resolve_component_to_structural(component: str) -> str:
    """
    Map component path/filename to structural node ID.
    
    Examples:
    - "protocol_provider.py" -> "0.6.4.3.f"
    - "FabricClient" -> "0.6" (wiring domain)
    - "wiring/assembler.py" -> "0.6.1.f"
    """
    # This requires lookup against structural taxonomy
    # Placeholder for now - will use existing mapping logic
    return component
```

**Output Schema**:
```json
[
  {
    "id": "Task_Debug_TST-BG-001",
    "node_type": "task_debug",
    "target_structural_id": "tests/test_live_protocol_switch.py",
    "source_component_id": "TST-BG-001",
    "bug_type": "ImportError",
    "severity": "critical"
  }
]
```

---

## 3. Task Status Updater

**Input Schema**: Task node with status change
```json
{
  "task_id": "Task_Impl_0.1.2.4.f",
  "new_status": "completed",
  "completed_at": "2026-05-31T12:00:00"
}
```

**Parser Logic**:
```python
# parsers/task_updater.py
from datetime import datetime

def update_task_status(tasks: dict, task_id: str, status: str) -> dict:
    """
    Update task status and propagate changes to structural graph.
    
    On "completed" status:
    - Demote task (mark for removal)
    - Promote target stub to file
    """
    task = tasks.get(task_id)
    if not task:
        return tasks
    
    task["status"] = status
    task["updated_at"] = datetime.now().isoformat()
    
    if status == "completed":
        task["completed_at"] = datetime.now().isoformat()
        task["to_remove"] = True  # Mark for cleanup
    
    return tasks
```

**Output Schema** (updated task):
```json
{
  "Task_Impl_0.1.2.4.f": {
    "id": "Task_Impl_0.1.2.4.f",
    "status": "completed",
    "completed_at": "2026-05-31T12:00:00",
    "to_remove": true
  }
}
```

---

## 4. Task Priority Calculator

**Input Schema**: Multiple concern severities
```json
["SEC-001", "OBS-001", "NET-005"]  // Concern IDs
```

**Parser Logic**:
```python
# parsers/priority_calc.py
def calculate_priority(concern_ids: list[str], concerns_lookup: dict) -> str:
    """
    Calculate task priority based on highest concern severity.
    
    Priority order: critical > high > medium > low
    """
    priority_order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    max_priority = "low"
    
    for cid in concern_ids:
        concern = concerns_lookup.get(cid, {})
        sev = concern.get("severity", "low").lower()
        if priority_order.get(sev, 0) > priority_order.get(max_priority, 0):
            max_priority = sev
    
    return max_priority
```

## Master Tasks Parser

```python
# parsers/unified_tasks.py
def build_tasks_graph(structural_nodes: dict, concerns: dict) -> dict:
    """
    Master function to build complete tasks graph.
    
    Returns:
    {
        "tasks": [...],
        "edges": {
            "requires": {"task_id": ["task_id"]},
            "targets": {"task_id": "structural_id"}
        }
    }
    """
    # Get stubs
    stubs = [n for n in structural_nodes.values() if n.get("node_type") == "file_stub"]
    
    # Create implementation tasks
    impl_tasks = create_implementation_tasks(stubs, concerns)
    
    # Load debug tasks
    debug_tasks = []
    for csv_path in (roadmap_dir / "buggy_components").glob("*.csv"):
        debug_tasks.extend(parse_buggy_components(csv_path))
    
    # Combine and build edges
    all_tasks = {t["id"]: t for t in impl_tasks + debug_tasks}
    
    return {
        "tasks": all_tasks,
        "edges": build_task_edges(impl_tasks, debug_tasks)
    }
```

## Schema References

Each processing stage has detailed schema definitions in:
- `Inputs_Outputs_schema/tasks_graph_pipeline_Mapped_Schemas.csv` - Stage-by-stage input/output schemas
- See `Schema_Matrix_Cross_Reference.md` for node type mappings