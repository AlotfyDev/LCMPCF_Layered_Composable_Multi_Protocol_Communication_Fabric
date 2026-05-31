# Structural Graph Processing Pipeline

## Overview

The structural graph pipeline transforms CSV data into a hierarchical taxonomy with depth chains. This is the foundational processing step.

## Processing Steps

### Step 1: Load Domains

**Input**: `domains.csv`
```csv
element_number,element_name
0.1,network
0.2,transport
...
L1.2,security
```

**Output**: List of domain objects
```json
[
  {
    "id": "0.1",
    "name": "network"
  },
  {
    "id": "0.2", 
    "name": "transport"
  }
  // ...
]
```

---

### Step 2: Load Subdomains

**Input**: `subdomains.csv`
```csv
element_number,element_name,parent_domain
0.1.1,adapters,0.1
0.1.2,algorithms,0.1
...
L1.2.5,logging,L1.2
```

**Output**: List of subdomain objects
```json
[
  {
    "id": "0.1.1",
    "name": "adapters",
    "parent": "0.1"
  },
  {
    "id": "L1.2.5",
    "name": "logging", 
    "parent": "L1.2"
  }
  // ...
]
```

---

### Step 3: Load Files

**Input**: `files.csv` (enhanced with new columns)
```csv
element_number,element_name,full_path,classification,development_state,architectural_state,required_concerns
0.1.2.f,protocol.py,network/protocol.py,Exists,production-grade,current
0.1.2.4.f,weighted_round_robin.py,network/algorithms/weighted_round_robin.py,To_Be_Implemented,not_started,current,NET-005
```

**Output**: List of file objects with extracted hierarchy
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
  },
  {
    "id": "0.1.2.4.f",
    "name": "weighted_round_robin.py",
    "parent": "0.1.2",
    "path": "network/algorithms/weighted_round_robin.py",
    "node_type": "file_stub",
    "classification": "To_Be_Implemented",
    "development_state": "not_started",
    "architectural_state": "current",
    "required_concerns": "NET-005"
  }
]
```

---

### Step 4: Build Hierarchy Nodes

**Input**: Combined domains, subdomains, files lists

**Processing**:
- Assign depth levels (1=domain, 2=subdomain, 3=file)
- Compute `depth_chain` (path from root)
- Compute `ancestors_chain` (reverse path to root)

**Output**: Taxonomy nodes dictionary
```json
{
  "nodes": {
    "0.1": {
      "id": "0.1",
      "name": "network",
      "node_type": "folder_domain",
      "depth": 1,
      "depth_chain": ["0.1"],
      "ancestors_chain": ["0.1"]
    },
    "0.1.2": {
      "id": "0.1.2",
      "name": "algorithms",
      "node_type": "folder_subdomain",
      "parent": "0.1",
      "depth": 2,
      "depth_chain": ["0.1", "0.1.2"],
      "ancestors_chain": ["0.1.2", "0.1"]
    },
    "0.1.2.4.f": {
      "id": "0.1.2.4.f",
      "name": "weighted_round_robin.py",
      "node_type": "file_stub",
      "parent": "0.1.2",
      "depth": 3,
      "depth_chain": ["0.1", "0.1.2", "0.1.2.4.f"],
      "ancestors_chain": ["0.1.2.4.f", "0.1.2", "0.1"]
    }
  },
  "edges": {
    "0.1": {"0.1.2"},
    "0.1.2": {"0.1.2.4.f"}
  }
}
```

---

### Step 5: Register Dependencies (Optional)

**Input**: `src/` directory with Python files

**Processing**:
- AST scan of all `.py` files
- Match file paths to taxonomy nodes
- Extract import statements
- Create `parent_of` edges from imports

**Output**: Updated nodes with dependency arrays
```json
{
  "0.1.2.f": {
    "id": "0.1.2.f",
    "node_type": "file",
    "depends_on": [],           // Filled from import scanning
    "depended_by": []           // Populated from reverse mapping
  }
}
```

---

### Step 6: Save Taxonomy JSON

**Input**: Complete taxonomy structure

**Output**: `.docs/taxonomy_structure.json`
```json
{
  "domains": [...],
  "subdomains": [...],
  "files": [...],
  "total_nodes": 130,
  "total_edges": 163,
  "dependency_edges": {...}
}
```

## Error Handling

| Stage | Error Type | Action |
|-------|------------|--------|
| Load CSV | Missing file | Skip with warning |
| Load CSV | Malformed row | Repair with `_repair_row()` |
| Build hierarchy | Missing parent | Set parent=null, log warning |
| Register deps | ImportError | Skip module, continue |
| Save JSON | Permission denied | Raise exception |