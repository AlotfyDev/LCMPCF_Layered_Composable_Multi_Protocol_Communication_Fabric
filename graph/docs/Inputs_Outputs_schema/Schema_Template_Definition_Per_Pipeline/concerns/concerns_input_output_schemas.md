# Concerns Graph - Schema Templates

## Input Schemas

### domain_gap_input_schema.json
```json
{
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "title": "Domain Gap CSV Input",
    "required": ["id", "domain", "severity"],
    "properties": {
        "id": {
            "type": "string",
            "pattern": "^[A-Z]+-[0-9]+$",
            "description": "Concern identifier (e.g., SEC-001, OBS-002)"
        },
        "domain": {
            "type": "string",
            "enum": ["security", "observability", "testing", "devops", "wiring_di", "gateway_sdk", "network_L3", "transport_L4", "session_L5", "presentation_L6", "protocols_L7"]
        },
        "category": {
            "type": "string",
            "enum": ["missing_component", "buggy_component", "design_gap", "validation_missing"]
        },
        "title": {
            "type": "string",
            "description": "Brief concern title"
        },
        "description": {
            "type": "string"
        },
        "severity": {
            "type": "string",
            "enum": ["critical", "high", "medium", "low"]
        },
        "status": {
            "type": "string",
            "enum": ["open", "in_progress", "closed", "wont_fix"],
            "default": "open"
        },
        "impact": {
            "type": "string",
            "description": "Business impact description"
        },
        "dependencies": {
            "type": "string",
            "description": "Concerns this depends on (semicolon or comma separated)"
        },
        "effort_estimate": {
            "type": "string",
            "pattern": "^[XSMLXL]+$",
            "description": "Effort: XS, S, M, L, XL"
        },
        "proposed_solution": {
            "type": "string"
        },
        "evidence": {
            "type": "string",
            "description": "File evidence supporting the concern"
        }
    }
}
```

## Output Schemas

### concern_node_schema.json
```json
{
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "title": "Concern Node",
    "required": ["id", "node_type", "domain", "severity"],
    "properties": {
        "id": {
            "type": "string",
            "pattern": "^[A-Z]+-[0-9]+$"
        },
        "node_type": {
            "type": "string",
            "const": "concern"
        },
        "domain": {
            "type": "string"
        },
        "category": {"type": "string"},
        "title": {"type": "string"},
        "description": {"type": "string"},
        "severity": {
            "type": "string",
            "enum": ["critical", "high", "medium", "low"]
        },
        "status": {"type": "string"},
        "impact": {"type": "string"},
        "dependencies_parsed": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Parsed list of concern dependency IDs"
        },
        "effort_estimate": {"type": "string"},
        "proposed_solution": {"type": "string"},
        "evidence": {"type": "string"},
        "affects_structural": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Structural node IDs this concern affects"
        }
    }
}
```

### concern_edge_schema.json
```json
{
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "title": "Concern Relationship Edge",
    "properties": {
        "concern_depends_on_concern": {
            "type": "object",
            "additionalProperties": {
                "type": "array",
                "items": {"type": "string"}
            },
            "description": "Concern A depends on Concern B"
        },
        "concern_affects_structural": {
            "type": "object",
            "additionalProperties": {
                "type": "array",
                "items": {"type": "string"}
            },
            "description": "Concern X affects Structural Y"
        }
    }
}
```