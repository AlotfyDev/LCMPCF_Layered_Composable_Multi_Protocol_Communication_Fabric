# Dependency Graph - Schema Templates

## Input Schemas

### python_module_input_schema.json
```json
{
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "title": "Python Module (from AST scan)",
    "required": ["id", "file_path", "domain"],
    "properties": {
        "id": {
            "type": "string",
            "description": "Relative path (e.g., wiring/assembler.py)"
        },
        "file_path": {
            "type": "string",
            "description": "Absolute filesystem path"
        },
        "domain": {
            "type": "string",
            "description": "First directory component (e.g., network, transport)"
        }
    },
    "description": "Extracted via ast.parse() from Python source files"
}
```

### import_edge_schema.json
```json
{
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "array",
    "title": "Import Edge from AST",
    "items": {
        "type": "array",
        "items": [
            {"type": "string", "description": "from_path"},
            {"type": "string", "description": "to_path"}
        ],
        "minItems": 2,
        "maxItems": 2
    },
    "description": "Raw (from_path, to_path) tuples from AST scan"
}
```

## Output Schemas

### dependency_registry_entry_schema.json
```json
{
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "title": "Dependency Registry Entry",
    "required": ["id", "type", "source", "target", "relationship_type"],
    "properties": {
        "id": {
            "type": "string",
            "pattern": "^rel_.+_depends_.+$"
        },
        "type": {
            "type": "string",
            "const": "dependency"
        },
        "source": {
            "type": "string",
            "description": "Source taxonomy node ID"
        },
        "target": {
            "type": "string",
            "description": "Target taxonomy node ID"
        },
        "relationship_type": {
            "type": "string",
            "const": "imports"
        },
        "source_path": {"type": "string"},
        "target_path": {"type": "string"}
    }
}
```

### cycle_report_schema.json
```json
{
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "title": "Dependency Cycle Report",
    "properties": {
        "cycles": {
            "type": "array",
            "items": {
                "type": "array",
                "items": {"type": "string"}
            }
        },
        "status": {
            "type": "string",
            "enum": ["clean", "has_cycles"]
        }
    }
}
```

### topological_order_schema.json
```json
{
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "title": "Topological Order",
    "properties": {
        "order": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Node IDs in dependency order (dependencies first)"
        },
        "cycles": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "__cycle__": {
                        "type": "array",
                        "items": {"type": "string"}
                    }
                }
            }
        }
    }
}
```