# Concerns Graph Parsers

## Overview

Parsers for transforming domain_gaps CSVs into concern analysis objects. Concerns are analytical perspectives that reference structural entities.

---

## 1. Domain Gap CSV Parser

**Input Schema**: `domain_gaps/*.csv` (multiple files)
```csv
(security.csv)
id,domain,category,title,description,severity,status,impact,dependencies,effort_estimate,proposed_solution,evidence,notes
SEC-001,security,missing_component,No TLS/mTLS Support,"...all channels unencrypted...","high","open","All traffic exposed...","TransportConfig","XL","Add TLSConfig...","tcp.py:64-65...","..."

(observability.csv) - with dependencies
OBS-002,observability,missing_component,OpenTelemetry Tracing,"...no OTel spans...","high","open","Cannot identify bottlenecks...","OBS-001","L","Add OpenTelemetry...","transport/context/...","..."
```

**Parser Logic**:
```python
# parsers/concerns_parser.py
import csv
from pathlib import Path

def parse_domain_gap_csv(filepath: Path) -> list[dict]:
    """
    Parse a single domain_gaps CSV into concern objects.
    
    Output Schema:
    [
        {
            "id": "string",           # e.g., "SEC-001"
            "node_type": "concern",
            "domain": "string",       # Cross-cutting domain
            "category": "string",
            "title": "string",
            "description": "string",
            "severity": "string",
            "status": "string",
            "impact": "string",
            "dependencies": "string",   # Raw - needs parsing
            "effort_estimate": "string",
            "proposed_solution": "string",
            "evidence": "string",
            "notes": "string"
        }
    ]
    """
    concerns = []
    with open(filepath, encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            concern = {
                "id": row["id"].strip(),
                "node_type": "concern",
                "domain": row["domain"].strip(),
                "category": row.get("category", "").strip(),
                "title": row.get("title", "").strip(),
                "description": row.get("description", "").strip(),
                "severity": row.get("severity", "").strip(),
                "status": row.get("status", "").strip(),
                "impact": row.get("impact", "").strip(),
                "dependencies": row.get("dependencies", "").strip(),
                "effort_estimate": row.get("effort_estimate", "").strip(),
                "proposed_solution": row.get("proposed_solution", "").strip(),
                "evidence": row.get("evidence", "").strip(),
                "notes": row.get("notes", "").strip()
            }
            concerns.append(concern)
    return concerns

def parse_all_domain_gaps(domain_gaps_dir: Path) -> list[dict]:
    """
    Parse all CSV files in domain_gaps directory.
    """
    all_concerns = []
    for csv_file in sorted(domain_gaps_dir.glob("*.csv")):
        all_concerns.extend(parse_domain_gap_csv(csv_file))
    return all_concerns
```

**Output Schema**:
 ```json
 [
   {
     "id": "SEC-001",
     "node_type": "concern",
     "domain": "security",
     "category": "missing_component",
     "title": "No TLS/mTLS Support",
     "severity": "high"
   }
 ]
 ```
 
 **Real Statistics**:
 - Total concerns: 131
 - Security: 9 concerns
 - Observability: 11 concerns
 - Testing: 15 concerns
 - DevOps: 10 concerns
 - Wiring/DI: 12 concerns
 - Gateway SDK: 8 concerns
 - Network L3: 12 concerns
 - Transport L4: 9 concerns
 - Session L5: 10 concerns
 - Presentation L6: 10 concerns
 - Protocols L7: 9 concerns

---

## 2. Dependency Parser (Concerns)

**Input Schema**: Raw dependencies string from concern
```csv
dependencies column values:
"TransportConfig"
"OBS-001"
"NET-002; NET-003"
"FabrricClient, ICommunicationGateway, protocol handlers"
```

**Parser Logic**:
```python
# parsers/concern_dependencies.py
def parse_concern_dependencies(raw: str) -> list[str]:
    """
    Parse concern dependencies field into list of concern IDs.
    
    Input: Raw CSV dependencies string
    Output: List of concern identifier strings
    """
    if not raw or not raw.strip():
        return []
    
    tokens = []
    # Split by semicolon, comma, or whitespace
    for part in raw.split(";"):
        for subpart in part.split(","):
            for token in subpart.strip().split():
                token = token.strip()
                if token and token.lower() != "none":
                    tokens.append(token)
    return tokens
```

**Output Schema**:
```json
["OBS-001", "NET-002", "NET-003"]
```

---

## 3. Concern-to-Structural Linker

**Input Schema**: 
- Concerns list with `dependencies` and `evidence` fields
- Structural taxonomy with `required_concerns` and `path` fields

**Evidence-Based Linking Logic**:
```python
# parsers/concern_linker.py
import re

def extract_target_path(concern: dict, structural_nodes: dict) -> list[str]:
    """
    Extract file paths from concern evidence/proposed_solution.
    
    Input concern evidence examples:
    - "tcp.py:64-65: asyncio.open_connection() without ssl_context"
    - "wiring/config/loader.py:67-139: load_config reads YAML..."
    - "transport_example.yaml uses nested keys..."
    
    Output: List of matching structural node IDs
    """
    evidence = concern.get("evidence", "") + concern.get("proposed_solution", "")
    
    # Find .py file references
    path_refs = re.findall(r'\w+(?:/\w+)*\.py', evidence)
    
    matched_nodes = []
    for ref in path_refs:
        for tax_id, node in structural_nodes.items():
            if node.get("node_type") in ("file", "file_stub"):
                node_path = node.get("path", "")
                if ref in node_path or node_path.endswith(ref):
                    matched_nodes.append(tax_id)
    
    return matched_nodes
```

**Output Schema** (affects relationships):
```json
{
  "SEC-001": {
    "id": "SEC-001",
    "affects_structural": ["0.2.11.f", "0.2.14.f"]  // tcp.py, websocket.py
  }
}
```

---

## 4. Concern Severity Normalizer

**Input Schema**: Raw severity strings
```csv
severity column values:
"high"
"critical"  
"medium"
MEDIUM (inconsistent case)
vital (should map to high)
```

**Parser Logic**:
```python
# parsers/severity_normalizer.py
def normalize_severity(raw: str) -> str:
    """
    Normalize severity values to canonical enum.
    
    Input: "vital", "HIGH", "Medium", etc.
    Output: "critical", "high", "medium", "low"
    """
    if not raw:
        return "medium"
    
    severity_map = {
        "vital": "high",
        "open": "open"  # Keep status values separate
    }
    raw_lower = raw.lower().strip()
    return severity_map.get(raw_lower, raw_lower)
```

**Output Schema**:
```json
"SEC-001": {
  "severity": "high"
}
```

---

## Unified Concerns Parser

**Master Parser Logic**:
```python
# parsers/unified_concerns.py
def build_concerns_graph(roadmap_dir: Path, structural_nodes: dict) -> dict:
    """
    Master function to build complete concerns graph.
    
    Returns:
    {
        "concerns": [...],
        "affects_edges": {"concern_id": ["structural_id", ...]},
        "dependencies_edges": {"concern_id": ["concern_id", ...]}
    }
    """
    concerns = parse_all_domain_gaps(roadmap_dir / "domain_gaps")
    
    affects_edges = {}
    dep_edges = {}
    
    for concern in concerns:
        # Parse dependencies
        cid = concern["id"]
        dep_edges[cid] = parse_concern_dependencies(concern.get("dependencies", ""))
        
        # Link to structural nodes via required_concerns matching
        # OR via evidence parsing
        affects = extract_target_path(concern, structural_nodes)
        affects_edges[cid] = affects
    
    return {
        "concerns": concerns,
        "affects_edges": affects_edges,
        "dependencies_edges": dep_edges
    }
```

## Schema References

Each processing stage has detailed schema definitions in:
- `Inputs_Outputs_schema/concerns_graph_pipeline_Mapped_Schemas.csv` - Stage-by-stage input/output schemas
- See `Schema_Matrix_Cross_Reference.md` for edge type mappings

## Error Handling

| Error Type | Action |
|------------|--------|
| Missing domain_gaps dir | Return empty concerns list |
| Malformed CSV row | Apply repair logic, log row |
| Unresolved dependency | Skip, log orphaned concern |
| No structural match | Keep concern orphaned, will be addressed manually |