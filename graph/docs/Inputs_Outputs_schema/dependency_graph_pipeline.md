# Dependency Graph Processing Pipeline

## Overview

The dependency graph analyzes runtime import relationships between **implemented files only**. This graph enables impact analysis, cycle detection, and build ordering. File stubs are excluded because their dependencies are unknown until implementation.

## Processing Steps

### Step 1: Get Implemented File Nodes

**Input**: Structural taxonomy nodes (filtered)
```json
// From taxonomy_structure.json
{
  "nodes": {
    "0.1.2.f": {
      "id": "0.1.2.f",
      "node_type": "file",  // Only "file", exclude "file_stub"
      "path": "network/protocol.py",
      "depth_chain": ["0.1", "0.1.2", "0.1.2.f"]
    },
    "0.6.1.f": {
      "id": "0.6.1.f",
      "node_type": "file",
      "path": "wiring/assembler.py", 
      "depth_chain": ["0.6", "0.6.1.f"]
    }
  }
}
```

**Processing**:
- Filter taxonomy nodes where `node_type == "file"`
- Build path-to-ID lookup table

**Output**: Implemented files list with path mapping
```json
{
  "implemented_files": [
    {
      "id": "0.1.2.f",
      "path": "network/protocol.py"
    }
  ],
  "path_to_id": {
    "network/protocol.py": "0.1.2.f",
    "wiring/assembler.py": "0.6.1.f"
  }
}
```

---

### Step 2: Scan Source Code for Imports

**Input**: `src/` directory with Python source files

**Processing**:
- Use AST to parse each `.py` file
- Extract `ast.Import` and `ast.ImportFrom` statements
- Resolve module paths to filesystem paths
- Map to taxonomy node IDs

**AST Extraction Example**:
```python
# src/wiring/assembler.py contains:
# from network.protocol import load_config
# import asyncio

# Extracted imports:
[
  ("wiring/assembler.py", "network/protocol.py"),  # Resolved from import
  ("wiring/assembler.py", "asyncio")  # External, ignored
]
```

**Output**: Import edges from source analysis
```json
[
  {
    "from_path": "wiring/assembler.py",
    "to_path": "network/protocol.py",
    "from_tax_id": "0.6.1.f",
    "to_tax_id": "0.1.2.f"
  }
]
```

---

### Step 3: Register Dependencies in Taxonomy

**Input**: Import edges with taxonomy IDs

**Processing**:
- Add `to_tax_id` to `from_tax_id`'s `depends_on` array
- Add `from_tax_id` to `to_tax_id`'s `imported_by` array
- Skip imports to external packages (not in taxonomy)

**Output**: Updated file nodes with dependencies
```json
{
  "0.6.1.f": {
    "id": "0.6.1.f",
    "node_type": "file",
    "path": "wiring/assembler.py",
    "depends_on": ["0.1.2.f", "0.6.4.1.f"],
    "imported_by": []
  },
  "0.1.2.f": {
    "id": "0.1.2.f",
    "node_type": "file", 
    "path": "network/protocol.py",
    "depends_on": [],
    "imported_by": ["0.6.1.f", "0.2.1.f"]
  }
}
```

---

### Step 4: Build Dependency Edges

**Input**: File nodes with populated `depends_on` arrays

**Processing**:
- Create bidirectional edges
- Validate all referenced nodes exist in taxonomy

**Output**: Dependency graph structure
```json
{
  "edges": {
    "0.6.1.f": ["0.1.2.f", "0.6.4.1.f"],  // assembler imports
    "0.1.2.f": []  // protocol has no internal imports
  },
  "reverse_edges": {
    "0.1.2.f": ["0.6.1.f", "0.2.1.f"],  // protocol is imported by
    "0.6.4.1.f": ["0.6.1.f"]
  }
}
```

---

### Step 5: Cycle Detection

**Input**: Dependency edges graph

**Processing**:
- DFS traversal with color marking (WHITE/GRAY/BLACK)
- Detect back edges indicating cycles
- Report cycle paths

**Output**: Cycle report or clean status
```json
// Example: No cycles detected
{
  "cycles": [],
  "status": "clean"
}

// Example: Cycles detected
{
  "cycles": [
    ["0.1.2.f", "0.3.1.f", "0.1.2.f"]  // cycle: protocol → session → protocol
  ],
  "status": "has_cycles"
}
```

---

### Step 6: Topological Sort

**Input**: Dependency edges graph (cycle-free)

**Processing**:
- Kahn's algorithm for topological ordering
- Handle nodes with no dependencies first
- Ensure all dependencies satisfied before dependent

**Output**: Ordered implementation list
```json
[
  "0.1.2.f",  // No dependencies, implement first
  "0.1.1.f",  // No dependencies
  "0.6.4.1.f", // Only depends on already-implemented
  "0.6.1.f"   // Depends on 0.1.2.f and 0.6.4.1.f
]
```

---

### Step 7: Impact Analysis

**Input**: Target file ID, transitive depth

**Processing**:
- Find all nodes that transitively depend on target
- Walk reverse edges to build impact tree
- Limit to specified depth

**Output**: Impact tree
```json
{
  "root": "network/protocol.py",
  "levels": {
    "0": [
      {
        "id": "0.1.2.f",
        "name": "protocol.py",
        "depended_by_count": 5
      }
    ],
    "1": [
      {
        "id": "0.6.1.f", 
        "name": "assembler.py",
        "depended_by_count": 3
      },
      {
        "id": "0.2.1.f",
        "name": "transport/__init__.py", 
        "depended_by_count": 2
      }
    ],
    "2": [
      {
        "id": "0.7.2.f",
        "name": "fastapi_router.py",
        "depended_by_count": 1
      }
    ]
  }
}
```

---

### Step 8: Find Critical Path

**Input**: All file nodes with dependency counts

**Processing**:
- Calculate in-degree for each node (from `imported_by`)
- Find nodes with highest cumulative impact
- Trace paths through high-impact nodes

**Output**: Critical implementation path
```json
{
  "critical_path": [
    "0.1.2.f",    // protocol.py - many dependents
    "0.6.1.f",    // assembler.py - central composition
    "0.7.2.f"     // fastapi_router.py - entry point
  ],
  "explanation": "These files have the highest transitive dependent count"
}
```

## Key Constraint

**File stubs are EXCLUDED** from dependency analysis because:
1. They don't exist yet - no code to scan
2. Dependencies unknown until implementation
3. Including them would create false positives in impact analysis

This is why we maintain separation between structural taxonomy (includes stubs) and dependency graph (implemented files only).

---

## Concern Integration

### Step 9: Link Concerns to Structural Nodes

**Input**: 
- Concerns from `domain_gaps/*.csv` (131 total)
- Structural taxonomy nodes with `required_concerns` field

**Processing**:
- Match concern IDs in `required_concerns` to concern nodes
- Create `affects` edges: concern → structural node
- Extract target paths from concern `evidence`/`proposed_solution`

**Output**: Concern-to-structural relationships
```json
{
  "NET-005": ["0.1.2.4.f", "0.1.2.5.f", "0.1.2.6.f"],
  "SEC-006": ["L1.2.5.1.f"],
  "OBS-001": ["0.6.2.3.f"]
}
```

**Statistics**: Out of 131 concerns, 97 are linked to structural nodes via:
- `required_concerns` field matching
- Path extraction from evidence text