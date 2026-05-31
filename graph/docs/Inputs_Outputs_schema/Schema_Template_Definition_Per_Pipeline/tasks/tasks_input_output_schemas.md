# Tasks Graph - Schema Templates

## Input Schemas

### task_stub_input_schema.json
```json
{
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "title": "Task Input from File Stub",
    "required": ["id", "required_concerns"],
    "properties": {
        "id": {
            "type": "string",
            "description": "Original file stub ID (e.g., 0.1.2.4.f)"
        },
        "name": {"type": "string"},
        "path": {"type": "string"},
        "required_concerns": {
            "type": "string",
            "description": "Comma-separated concern IDs"
        }
    },
    "description": "Derived from file_stub nodes in taxonomy"
}
```

### buggy_component_input_schema.json
```json
{
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "title": "Buggy Component CSV Input",
    "required": ["id", "component"],
    "properties": {
        "id": {"type": "string"},
        "component": {
            "type": "string",
            "description": "File path or component name with bug"
        },
        "bug_type": {
            "type": "string",
            "enum": ["ImportError", "logic_error", "missing_test", "performance", "memory_leak"]
        },
        "severity": {"type": "string"},
        "title": {"type": "string"},
        "description": {"type": "string"},
        "proposed_fix": {"type": "string"},
        "evidence": {"type": "string"}
    }
}
```

## Output Schemas

### task_node_schema.json
```json
{
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "title": "Task Node",
    "required": ["id", "node_type", "status", "priority"],
    "properties": {
        "id": {
            "type": "string",
            "pattern": "^Task_(Impl|Debug)_.+$"
        },
        "node_type": {
            "type": "string",
            "enum": ["task_implement", "task_debug"]
        },
        "target_structural_id": {
            "type": "string",
            "description": "Original structural node ID (e.g., 0.1.2.4.f)"
        },
        "target_path": {"type": "string"},
        "priority": {
            "type": "string",
            "enum": ["critical", "high", "medium", "low"]
        },
        "status": {
            "type": "string",
            "enum": ["not_started", "in_progress", "completed", "blocked"],
            "default": "not_started"
        },
        "effort_estimate": {
            "type": "string",
            "enum": ["XS", "S", "M", "L", "XL", "XXL"]
        },
        "required_concerns": {
            "type": "array",
            "items": {"type": "string"}
        }
    }
}
```

### task_edge_schema.json
```json
{
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "title": "Task Relationships",
    "properties": {
        "requires": {
            "type": "object",
            "description": "Task A requires Task B",
            "additionalProperties": {
                "type": "array",
                "items": {"type": "string"}
            }
        },
        "targets": {
            "type": "object",
            "description": "Task maps to structural node",
            "additionalProperties": {"type": "string"}
        }
    }
}
```

### task_status_update_schema.json
```json
{
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "title": "Task Status Update",
    "required": ["task_id", "new_status"],
    "properties": {
        "task_id": {"type": "string"},
        "new_status": {
            "type": "string",
            "enum": ["not_started", "in_progress", "completed", "blocked"]
        },
        "completed_at": {"type": "string", "format": "date-time"},
        "to_remove": {"type": "boolean"}
    }
}
```