# Structural Graph - Schema Templates

## Input Schemas

### domain_input_schema.json
```json
{
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "title": "Domain CSV Input",
    "required": ["element_number", "element_name"],
    "properties": {
        "element_number": {
            "type": "string",
            "pattern": "^[0-9]+(\\.[0-9]+)*$",
            "description": "Hierarchical ID (e.g., '0.1', '0.2')"
        },
        "element_name": {
            "type": "string",
            "minLength": 1,
            "description": "Human-readable domain name"
        }
    }
}
```

### subdomain_input_schema.json
```json
{
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "title": "Subdomain CSV Input",
    "required": ["element_number", "element_name", "parent_domain"],
    "properties": {
        "element_number": {
            "type": "string",
            "pattern": "^[0-9]+(\\.[0-9]+)*\\.[0-9]+$",
            "description": "Hierarchical ID (e.g., '0.1.1')"
        },
        "element_name": {
            "type": "string",
            "minLength": 1,
            "description": "Human-readable subdomain name"
        },
        "parent_domain": {
            "type": "string",
            "pattern": "^[0-9]+(\\.[0-9]+)*$",
            "description": "Parent domain element_number"
        }
    }
}
```

### file_input_schema.json
```json
{
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "title": "File CSV Input",
    "required": ["element_number", "element_name", "full_path"],
    "properties": {
        "element_number": {
            "type": "string",
            "pattern": "^[0-9]+(\\.[0-9]+)*\\.f$",
            "description": "File node ID ending in .f"
        },
        "element_name": {
            "type": "string",
            "description": "File name"
        },
        "full_path": {
            "type": "string",
            "description": "Filesystem path relative to src/"
        },
        "classification": {
            "type": "string",
            "enum": ["Exists", "To_Be_Implemented"],
            "default": "Exists"
        },
        "development_state": {
            "type": "string",
            "enum": ["production-grade", "tested", "implemented", "scaffold", "stub"],
            "default": "production-grade"
        },
        "architectural_state": {
            "type": "string",
            "enum": ["current", "deprecated", "needs-redesign", "deleted"],
            "default": "current"
        },
        "required_concerns": {
            "type": "string",
            "description": "Comma-separated concern IDs this file addresses"
        }
    }
}
```

## Output Schemas

### taxonomy_node_schema.json
```json
{
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "title": "Taxonomy Node",
    "required": ["id", "node_type", "name", "depth"],
    "properties": {
        "id": {
            "type": "string",
            "description": "Unique node identifier"
        },
        "node_type": {
            "type": "string",
            "enum": ["folder_domain", "folder_subdomain", "file", "file_stub", "concern"]
        },
        "name": {
            "type": "string"
        },
        "parent": {
            "type": ["string", "null"]
        },
        "depth": {
            "type": "integer",
            "minimum": 1,
            "maximum": 3
        },
        "depth_chain": {
            "type": "array",
            "items": {"type": "string"}
        },
        "ancestors_chain": {
            "type": "array",
            "items": {"type": "string"}
        }
    }
}
```

### taxonomy_edges_schema.json
```json
{
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "title": "Taxonomy Edges",
    "additionalProperties": {
        "type": "array",
        "items": {"type": "string"}
    },
    "description": "Mapping of parent_id -> [child_id, ...]"
}
```

## Pipeline Output Schema

### taxonomy_structure_output_schema.json
```json
{
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "title": "Taxonomy Structure Export",
    "required": ["domains", "subdomains", "files", "concerns", "total_nodes", "total_edges"],
    "properties": {
        "domains": {
            "type": "array",
            "items": {"$ref": "#/definitions/taxonomy_node"}
        },
        "subdomains": {
            "type": "array",
            "items": {"$ref": "#/definitions/taxonomy_node"}
        },
        "files": {
            "type": "array",
            "items": {"$ref": "#/definitions/file_node"}
        },
        "concerns": {
            "type": "array",
            "items": {"$ref": "#/definitions/concern_node"}
        },
        "total_nodes": {"type": "integer"},
        "total_edges": {"type": "integer"},
        "dependency_edges": {"type": "object"}
    },
    "definitions": {
        "taxonomy_node": {
            "type": "object",
            "required": ["id", "node_type", "depth", "depth_chain", "ancestors_chain"]
        },
        "file_node": {
            "allOf": [{"$ref": "#/definitions/taxonomy_node"}],
            "properties": {
                "path": {"type": "string"},
                "required_concerns": {"type": "string"}
            }
        },
        "concern_node": {
            "allOf": [{"$ref": "#/definitions/taxonomy_node"}],
            "properties": {
                "domain": {"type": "string"},
                "severity": {"type": "string"}
            }
        }
    }
}
```