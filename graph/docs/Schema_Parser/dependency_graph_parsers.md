# Dependency Graph Parsers

## Overview

Parsers for extracting runtime import relationships from source code. This is the only parser that analyzes actual code rather than CSV data. It operates on implemented files only (excludes stubs).

---

## 1. AST Module Scanner

**Input Schema**: Python source files in `src/`
```python
# Example source file content:
# src/wiring/assembler.py
from network.protocol import load_config
from transport.factory import build_transport
import asyncio

# src/network/protocol.py  
def load_config(): ...
```

**Parser Logic**:
```python
# parsers/dependency_scanner.py
import ast
from pathlib import Path

def scan_source_modules(src_dir: Path) -> tuple[list[dict], list[tuple[str, str]]]:
    """
    Scan all Python files and extract module/import information.
    
    Returns:
    (
        module_nodes,          # List of module info dicts
        import_edges           # List of (from_path, to_path) tuples
    )
    """
    module_nodes = []
    import_edges = []
    
    for py_file in sorted(src_dir.rglob("*.py")):
        rel_path = py_file.relative_to(src_dir).as_posix()
        
        # Skip obsolete files
        if ".obsolete" in rel_path:
            continue
            
        try:
            with open(py_file, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read())
        except SyntaxError:
            continue
        
        # Extract imports
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    target = _resolve_module(alias.name, src_dir)
                    if target:
                        import_edges.append((rel_path, target))
                        
            elif isinstance(node, ast.ImportFrom):
                parts = _resolve_from_node(node, rel_path)
                if parts:
                    full_module = ".".join(parts)
                    target = _resolve_module(full_module, src_dir)
                    if target:
                        import_edges.append((rel_path, target))
        
        # Create module node
        domain = rel_path.split("/")[0]
        module_nodes.append({
            "id": rel_path,
            "type": "module",
            "domain": domain,
            "file_path": str(py_file)
        })
    
    return module_nodes, import_edges

def _resolve_from_node(node, rel_path):
    """Resolve ImportFrom node to module path parts."""
    parts = []
    if node.level:  # Relative imports
        file_parts = rel_path.split("/")
        base = file_parts[:-1]
        for _ in range(node.level - 1):
            if base:
                base.pop()
        parts = base
    if node.module:
        parts.extend(node.module.split("."))
    return parts

def _resolve_module(name, src_dir):
    """Resolve module name to relative path."""
    path = name.replace(".", "/")
    candidates = [
        src_dir / f"{path}.py",
        src_dir / path / "__init__.py"
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.relative_to(src_dir).as_posix()
    return None
```

**Output Schema**:
```json
{
  "modules": [
    {
      "id": "wiring/assembler.py",
      "type": "module",
      "domain": "wiring",
      "file_path": "D:/.../src/wiring/assembler.py"
    }
  ],
  "imports": [
    ["wiring/assembler.py", "network/protocol.py"],
    ["wiring/assembler.py", "transport/factory.py"]
  ]
}
```

---

## 2. Import-to-Taxonomy Mapper

**Input Schema**: 
- Import edges from AST scanner
- Structural taxonomy nodes (file type only)

**Parser Logic**:
```python
# parsers/import_mapper.py
def map_imports_to_taxonomy(import_edges: list[tuple], taxonomy_nodes: dict) -> dict:
    """
    Map raw import paths to taxonomy node IDs.
    
    Returns:
    {
        "from_tax_id": ["to_tax_id", ...],
        ...
    }
    """
    path_to_taxonomy_id = {}
    
    # Build lookup from taxonomy
    for tax_id, node in taxonomy_nodes.items():
        if node.get("node_type") == "file":  # Only implemented files
            path_to_taxonomy_id[node["path"]] = tax_id
    
    mapped_edges = {}
    for from_path, to_path in import_edges:
        from_tax = path_to_taxonomy_id.get(from_path)
        to_tax = path_to_taxonomy_id.get(to_path)
        
        if from_tax and to_tax:
            if from_tax not in mapped_edges:
                mapped_edges[from_tax] = []
            mapped_edges[from_tax].append(to_tax)
    
    return mapped_edges
```

**Output Schema**:
```json
{
  "0.6.1.f": ["0.1.2.f", "0.2.7.f"],
  "0.1.2.f": [],
  "0.2.7.f": ["0.2.1.f"]
}
```

---

## 3. Dependency Registration

**Input Schema**: Mapped import edges

**Parser Logic**:
```python
# parsers/dependency_registration.py
def register_file_dependencies(taxonomy_nodes: dict, import_edges: dict) -> dict:
    """
    Populate depends_on and imported_by arrays in taxonomy nodes.
    
    Input taxonomy node (before):
    {
      "id": "0.6.1.f",
      "node_type": "file",
      "depends_on": []
    }
    
    Output taxonomy node (after):
    {
      "id": "0.6.1.f",
      "node_type": "file",
      "depends_on": ["0.1.2.f", "0.2.7.f"],
      "imported_by": []
    }
    """
    # Initialize arrays
    for tax_id in taxonomy_nodes:
        if "depends_on" not in taxonomy_nodes[tax_id]:
            taxonomy_nodes[tax_id]["depends_on"] = []
        if "imported_by" not in taxonomy_nodes[tax_id]:
            taxonomy_nodes[tax_id]["imported_by"] = []
    
    # Register forward dependencies
    for from_tax, to_taxes in import_edges.items():
        if from_tax in taxonomy_nodes:
            taxonomy_nodes[from_tax]["depends_on"].extend(to_taxes)
    
    # Register reverse dependencies (imported_by)
    for from_tax, to_taxes in import_edges.items():
        for to_tax in to_taxes:
            if to_tax in taxonomy_nodes:
                taxonomy_nodes[to_tax]["imported_by"].append(from_tax)
    
    return taxonomy_nodes
```

**Output Schema**:
```json
{
  "0.6.1.f": {
    "depends_on": ["0.1.2.f", "0.2.7.f"],
    "imported_by": ["0.7.2.f", "0.6.6.3.f"]
  },
  "0.1.2.f": {
    "depends_on": [],
    "imported_by": ["0.6.1.f", "0.2.1.f"]
  }
}
```

---

## 4. Cycle Detection Parser

**Input Schema**: Dependency edges graph

**Parser Logic**:
```python
# parsers/cycle_detector.py
def detect_dependency_cycles(taxonomy_nodes: dict, edges: dict) -> list[list[str]]:
    """
    Detect cycles using DFS with color marking.
    
    Algorithm:
    - WHITE (0): Not visited
    - GRAY (1): Currently being processed  
    - BLACK (2): Fully processed
    
    Returns: List of cycles found (each cycle is a list of node IDs)
    """
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {nid: WHITE for nid in taxonomy_nodes if taxonomy_nodes[nid].get("node_type") == "file"}
    parent = {}
    cycles = []
    
    def dfs(nid):
        color[nid] = GRAY
        for dep_id in edges.get(nid, []):
            if dep_id not in color:
                continue
            if color[dep_id] == GRAY:
                # Found cycle
                cycle = []
                cur = nid
                while cur != dep_id:
                    cycle.append(cur)
                    cur = parent.get(cur)
                    if cur is None:
                        break
                cycle.append(dep_id)
                cycle.reverse()
                cycles.append(cycle)
            elif color[dep_id] == WHITE:
                parent[dep_id] = nid
                dfs(dep_id)
        color[nid] = BLACK
    
    for nid in color:
        if color[nid] == WHITE:
            dfs(nid)
    
    return cycles
```

**Output Schema**:
```json
[
  ["0.1.2.f", "0.3.1.f", "0.1.2.f"]  // Circular: network/protocol → session → network/protocol
]
```

---

## 5. Topological Sort Parser

**Input Schema**: Dependency edges graph (must be cycle-free)

**Parser Logic**:
```python
# parsers/topological_sort.py
from collections import deque

def topological_sort(taxonomy_nodes: dict, edges: dict) -> list[str]:
    """
    Kahn's algorithm for topological ordering.
    
    Returns nodes in dependency order (dependencies first).
    """
    # Filter to file nodes only
    file_nodes = {nid: n for nid, n in taxonomy_nodes.items() if n.get("node_type") == "file"}
    
    # Calculate in-degrees
    in_degree = {nid: 0 for nid in file_nodes}
    for from_id, to_ids in edges.items():
        if from_id in in_degree:
            for to_id in to_ids:
                if to_id in in_degree:
                    in_degree[to_id] += 1
    
    # Queue nodes with zero in-degree
    queue = deque([nid for nid, deg in in_degree.items() if deg == 0])
    result = []
    
    while queue:
        node = queue.popleft()
        result.append(node)
        
        for dep_id in edges.get(node, []):
            if dep_id in in_degree:
                in_degree[dep_id] -= 1
                if in_degree[dep_id] == 0:
                    queue.append(dep_id)
    
    # Check for remaining nodes (cycles)
    remaining = [nid for nid, deg in in_degree.items() if deg > 0]
    
    return result + [{"__cycle__": remaining}]
```

**Output Schema**:
```json
[
  "0.1.2.f",    // No dependencies
  "0.2.1.f",    // No dependencies
  "0.6.4.1.f",  // Depends on 0.1.2.f
  "0.6.1.f",    // Depends on 0.1.2.f, 0.6.4.1.f
  {"__cycle__": ["0.8.1.f", "0.6.1.f"]}  // Only if cycles exist
]
```

---

## Master Dependency Parser

```python
# parsers/unified_dependency.py
def build_dependency_graph(src_dir: Path, taxonomy_nodes: dict) -> dict:
    """
    Master function for complete dependency graph building.
    
    Returns:
    {
        "nodes": {...},        // Updated taxonomy nodes with dependencies
        "edges": {...},
        "cycles": [...]
    }
    """
    # Scan source
    modules, imports = scan_source_modules(src_dir)
    
    # Map to taxonomy
    edges = map_imports_to_taxonomy(imports, taxonomy_nodes)
    
    # Register dependencies
    taxonomy_nodes = register_file_dependencies(taxonomy_nodes, edges)
    
    # Detect cycles
    cycles = detect_dependency_cycles(taxonomy_nodes, edges)
    
    return {
        "nodes": taxonomy_nodes,
        "edges": edges,
        "cycles": cycles
    }
```

## Schema References

Each processing stage has detailed schema definitions in:
- `Inputs_Outputs_schema/dependency_graph_pipeline_Mapped_Schemas.csv` - Stage-by-stage input/output schemas
- See `Schema_Matrix_Cross_Reference.md` for edge type mappings