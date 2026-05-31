# Concerns Graph Processing Pipeline

## Overview

The concerns graph processes analytical perspectives from domain_gaps CSVs and creates relationships to structural nodes. Concerns are cross-cutting and reference multiple structural entities.

## Processing Steps

### Step 1: Load Domain Gap CSVs

**Input**: `domain_gaps/*.csv` (all CSV files in directory)
```csv
(security.csv)
id,domain,category,title,description,severity,status,impact,dependencies,effort_estimate,proposed_solution,evidence,notes
SEC-001,security,missing_component,No TLS/mTLS Support,"BaseTransporter sends plain bytes...",high,open,All traffic exposed...,TransportConfig,XL,Add TLSConfig to TransportConfig...

(observability.csv)  
OBS-001,observability,missing_component,Structured Logging Framework,"No unified logging system...",high,open,Debugging difficulty...,,"M,Adopt structlog or python-json-logger..."

(observability.csv - with concern dependency)
OBS-002,observability,missing_component,OpenTelemetry Distributed Tracing,"No tracing linking requests...",high,open,Cannot identify bottlenecks...,OBS-001,L,Add OpenTelemetry instrumentation...

(testing.csv)
TST-001,testing,missing_component,Zero Unit Tests Under src/,"No test files exist inside src/...",critical,open,Cannot guarantee stability...,,,XL,Create pytest unit/ structure...

(devops.csv)
DEV-001,devops,missing_component,No Dockerfile for FabricService,"Dockerfile template exists...",high,open,Cannot containerize...,,,S,Create Dockerfile at project root...
```

**Output**: List of concern objects
```json
[
  {
    "id": "SEC-001",
    "node_type": "concern",
    "domain": "security",
    "category": "missing_component",
    "title": "No TLS/mTLS Support",
    "description": "BaseTransporter sends plain bytes...",
    "severity": "high",
    "status": "open",
    "impact": "All traffic exposed...",
    "dependencies": "TransportConfig",
    "effort_estimate": "XL",
    "proposed_solution": "Add TLSConfig to TransportConfig...",
    "evidence": "...",
    "notes": ""
  }
  // ... all concerns from all CSVs
]
```

---

### Step 2: Normalize Concern Identifiers

**Input**: Raw concern IDs from CSVs

**Processing**:
- Parse `dependencies` field into list of concern IDs
- Map string identifiers to taxonomy node IDs

**Output**: Concerns with normalized references
```json
{
  "OBS-002": {
    "id": "OBS-002",
    "node_type": "concern",
    "domain": "observability",
    "severity": "high",
    "depends_on_concerns": ["OBS-001"],
    "affects_files": []  // To be populated in next step
  }
}
```

---

### Step 3: Link Concerns to Structural Nodes

**Input**: 
- Concerns list from Step 1
- Structural taxonomy nodes (file/file_stub) with `required_concerns` field

**Processing**:
- For each structural node, parse its `required_concerns` field
- Create `affects` relationship edge: concern → structural node

**Output**: Concerns with linked structural targets
```json
{
  "NET-005": {
    "id": "NET-005",
    "node_type": "concern",
    "domain": "network_L3",
    "affects_structural": ["0.1.2.4.f", "0.1.2.5.f", "0.1.2.6.f"]
  },
  "SEC-002": {
    "id": "SEC-002",
    "node_type": "concern",
    "domain": "security",
    "affects_structural": ["L1.2.2.1.f"]  // security_gateway.py stub
  }
}
```

**Real Statistics**: 
- Total concerns: 131
- Concerns linked to structural nodes: 97 (74% match rate)
- Unlinked concerns: 34 (cross-cutting concerns without concrete file targets)

---

### Step 4: Build Concern Hierarchy

**Input**: Concerns with relationships

**Processing**:
- Create `depends_on` edges between concerns
- Validate dependency chains (no cycles in concern dependencies)

**Output**: Concern graph with edges
```json
{
  "nodes": {
    "SEC-001": {"node_type": "concern", "domain": "security", ...},
    "SEC-002": {"node_type": "concern", "domain": "security", ...}
  },
  "edges": {
    "OBS-002": {"OBS-001"},  // OBS-002 depends on OBS-001
    "SEC-002": {"L1.2.2.1.f"}  // Concern affects structural node
  }
}
```

---

### Step 5: Severity and Impact Analysis

**Input**: Complete concern graph

**Processing**:
- Group by domain
- Count by severity
- Calculate impact scores

**Output**: Concern analysis report
```json
{
  "by_domain": {
    "security": {
      "total": 9,
      "by_severity": {"critical": 0, "high": 4, "medium": 3, "low": 2}
    },
    "observability": {
      "total": 11,
      "by_severity": {"critical": 1, "high": 4, "medium": 4, "low": 2}
    },
    "testing": {
      "total": 15,
      "by_severity": {"critical": 2, "high": 5, "medium": 3, "low": 0}
    },
    "devops": {
      "total": 10,
      "by_severity": {"critical": 0, "high": 6, "medium": 2, "low": 0}
    }
  },
  "critical_path": ["TST-001", "GWY-007", "GWY-001"]
}
```

---

### Step 6: Register Concern Targets (Integration)

**Input**: Structural taxonomy with file_stub nodes

**Processing**:
- Match concern's target path to structural node path
- Populate `affects_files` array on concern nodes

**Example Matching Logic**:
```python
# concern.target_path: "network/algorithms/weighted_round_robin.py"
# structural_node.path: "network/algorithms/weighted_round_robin.py"
# => Match found, add edge: concern.id -> structural_node.id
```

**Output**: Updated concern nodes with concrete file targets
```json
{
  "NET-005": {
    "id": "NET-005",
    "domain": "network_L3",
    "affects_files": ["0.1.2.4.f", "0.1.2.5.f", "0.1.2.6.f"]
  }
}
```

## Error Handling

| Stage | Error Type | Action |
|-------|------------|--------|
| Load CSV | Missing file | Skip domain, log warning |
| Parse row | Malformed CSV | Apply repair rules |
| Link concerns | Missing structural target | Log orphaned concern |
| Severity analysis | Unknown severity value | Default to "medium" |