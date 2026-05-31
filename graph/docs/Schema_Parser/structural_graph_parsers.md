# Structural Graph Parsers

## Overview

Parsers for transforming CSV data into the canonical structural taxonomy. These are the foundational parsers that create the single source of truth.

---

## 1. Domain Parser

**Input Schema**: `domains.csv`
```csv
element_number,element_name
0.1,network
L1.0,tests
```

**Parser Logic**:
```python
# parsers/domain_parser.py
def parse_domains(filepath: Path) -> list[dict]:
    """
    Parse domains.csv into domain objects.
    
    Output Schema:
    [
        {"id": "string", "name": "string"},
        ...
    ]
    """
    domains = []
    with open(filepath, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            domains.append({
                "id": row["element_number"].strip(),
                "name": row["element_name"].strip()
            })
    return domains
```

**Output Schema**:
```json
[
  {
    "id": "0.1",
    "name": "network"
  },
  {
    "id": "L1.2",
    "name": "security"
  }
]
```

---

## 2. Subdomain Parser

**Input Schema**: `subdomains.csv`
```csv
element_number,element_name,parent_domain
0.1.1,adapters,0.1
L1.2.5,logging,L1.2
```

**Parser Logic**:
```python
# parsers/subdomain_parser.py
def parse_subdomains(filepath: Path) -> list[dict]:
    """
    Parse subdomains.csv into subdomain objects.
    
    Output Schema:
    [
        {"id": "string", "name": "string", "parent": "string"},
        ...
    ]
    """
    subdomains = []
    with open(filepath, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            subdomains.append({
                "id": row["element_number"].strip(),
                "name": row["element_name"].strip(),
                "parent": row["parent_domain"].strip()
            })
    return subdomains
```

**Output Schema**:
```json
[
  {
    "id": "0.1.1",
    "name": "adapters",
    "parent": "0.1"
  }
]
```

---

## 3. File Parser (Enhanced)

**Input Schema**: `files.csv` (enhanced with new columns)
```csv
element_number,element_name,full_path,classification,development_state,architectural_state,required_concerns
0.1.2.f,protocol.py,network/protocol.py,Exists,production-grade,current,
0.1.2.4.f,weighted_round_robin.py,network/algorithms/weighted_round_robin.py,To_Be_Implemented,not_started,current,NET-005
L1.2.5.1.f,security_logger.py,security/logging/logger.py,To_Be_Implemented,not_started,current,SEC-006
```

**Parser Logic**:
```python
# parsers/file_parser.py
def parse_files(filepath: Path) -> list[dict]:
    """
    Parse files.csv into file objects with parent extraction.
    
    Output Schema:
    [
        {
            "id": "string",           # element_number
            "name": "string",         # element_name
            "parent": "string|null",  # Extracted from element_number
            "path": "string",         # full_path
            "node_type": "file|file_stub",
            "classification": "string",
            "development_state": "string",
            "architectural_state": "string",
            "required_concerns": "string"  # comma-separated
        },
        ...
    ]
    """
    files = []
    with open(filepath, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            elem_num = row["element_number"]
            
            # Extract parent from element_number
            # "0.1.2.4.f" -> parent "0.1.2"
            # "L1.2.5.1.f" -> parent "L1.2.5"
            if ".f" in elem_num:
                parts = elem_num.split(".f")[0].rsplit(".", 1)
                parent_id = parts[0] if len(parts) > 0 else None
            else:
                parent_id = None
            
            classification = row.get("classification", "Exists")
            files.append({
                "id": elem_num,
                "name": row["element_name"],
                "parent": parent_id,
                "path": row["full_path"],
                "node_type": "file_stub" if classification == "To_Be_Implemented" else "file",
                "classification": classification,
                "development_state": row.get("development_state", "production-grade"),
                "architectural_state": row.get("architectural_state", "current"),
                "required_concerns": row.get("required_concerns", "")
            })
    return files
```

**Output Schema**:
```json
[
  {
    "id": "0.1.2.f",
    "name": "protocol.py",
    "parent": "0.1",
    "path": "network/protocol.py",
    "node_type": "file",
    "classification": "Exists",
    "development_state": "production-grade",
    "architectural_state": "current",
    "required_concerns": ""
  }
]
```

---

## Unified Structural Parser

**Combined Parser Logic**:
```python
# parsers/structural_parser.py
def parse_structural_taxonomy(roadmap_dir: Path) -> dict:
    """
    Master function to parse all structural CSVs.
    
    Returns:
    {
        "domains": [...],
        "subdomains": [...], 
        "files": [...]
    }
    """
    domains = parse_domains(roadmap_dir / "domains.csv")
    subdomains = parse_subdomains(roadmap_dir / "subdomains.csv")
    files = parse_files(roadmap_dir / "files.csv")
    
    return {"domains": domains, "subdomains": subdomains, "files": files}
```

## Schema References

Each processing stage has detailed schema definitions in:
- `Inputs_Outputs_schema/structural_graph_pipeline_Mapped_Schemas.csv` - Stage-by-stage input/output schemas
- See `Schema_Matrix_Cross_Reference.md` for node type mappings

## Error Handling

| Error Type | Action |
|------------|--------|
| Missing CSV file | Return empty list, log warning |
| Malformed row | Apply `_repair_row()` logic |
| Missing parent | Set parent=null, log orphaned node |
| Duplicate ID | Keep last, log conflict |