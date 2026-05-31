"""
Dependency Graph Parsers

Analyze runtime import relationships using AST scanning of source code.
Only processes implemented files (not stubs).
"""
import ast
from pathlib import Path


def _resolve_module(name: str, src_dir: Path) -> str | None:
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


def _resolve_from_node(node: ast.ImportFrom, rel_path: str) -> list[str]:
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


def scan_source_modules(src_dir: Path) -> tuple[list[dict], list[tuple[str, str]]]:
    """
    Scan all Python files and extract module/import information.
    
    Returns: (module_nodes, import_edges)
    """
    module_nodes = []
    import_edges = []
    
    src = Path(src_dir)
    for py_file in sorted(src.rglob("*.py")):
        rel_path = py_file.relative_to(src).as_posix()
        
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
                    target = _resolve_module(alias.name, src)
                    if target:
                        import_edges.append((rel_path, target))
                        
            elif isinstance(node, ast.ImportFrom):
                parts = _resolve_from_node(node, rel_path)
                if parts:
                    full_module = ".".join(parts)
                    target = _resolve_module(full_module, src)
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


def map_imports_to_taxonomy(import_edges: list[tuple], taxonomy_nodes: dict) -> dict:
    """Map raw import paths to taxonomy node IDs."""
    path_to_taxonomy_id = {}
    
    # Build lookup from taxonomy (only implemented files)
    for tax_id, node in taxonomy_nodes.items():
        if node.get("node_type") == "file":
            path_to_taxonomy_id[node["path"]] = tax_id
    
    mapped_edges = {}
    for from_path, to_path in import_edges:
        from_tax = path_to_taxonomy_id.get(from_path)
        to_tax = path_to_taxonomy_id.get(to_path)
        
        if from_tax and to_tax:
            if from_tax not in mapped_edges:
                mapped_edges[from_tax] = []
            if to_tax not in mapped_edges[from_tax]:
                mapped_edges[from_tax].append(to_tax)
    
    return mapped_edges


def register_file_dependencies(taxonomy_nodes: dict, edges: dict) -> dict:
    """Populate depends_on and imported_by arrays in taxonomy nodes."""
    # Initialize arrays for file nodes
    for tax_id, node in taxonomy_nodes.items():
        if node.get("node_type") == "file":
            if "depends_on" not in node:
                node["depends_on"] = []
            if "imported_by" not in node:
                node["imported_by"] = []
    
    # Register forward dependencies
    for from_tax, to_taxes in edges.items():
        if from_tax in taxonomy_nodes:
            taxonomy_nodes[from_tax]["depends_on"] = list(set(
                taxonomy_nodes[from_tax].get("depends_on", []) + to_taxes
            ))
    
    # Register reverse dependencies
    for from_tax, to_taxes in edges.items():
        for to_tax in to_taxes:
            if to_tax in taxonomy_nodes:
                imported_by = taxonomy_nodes[to_tax].get("imported_by", [])
                if from_tax not in imported_by:
                    imported_by.append(from_tax)
                taxonomy_nodes[to_tax]["imported_by"] = imported_by
    
    return taxonomy_nodes


def detect_cycles(taxonomy_nodes: dict, edges: dict) -> list[list[str]]:
    """Detect cycles using DFS with color marking."""
    WHITE, GRAY, BLACK = 0, 1, 2
    file_nodes = {nid: n for nid, n in taxonomy_nodes.items() 
                  if n.get("node_type") == "file"}
    color = {nid: WHITE for nid in file_nodes}
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


def topological_sort(taxonomy_nodes: dict, edges: dict) -> list[str]:
    """Kahn's algorithm for topological ordering."""
    from collections import deque
    
    file_nodes = {nid: n for nid, n in taxonomy_nodes.items() 
                 if n.get("node_type") == "file"}
    
    in_degree = {nid: 0 for nid in file_nodes}
    for from_id, to_ids in edges.items():
        if from_id in in_degree:
            for to_id in to_ids:
                if to_id in in_degree:
                    in_degree[to_id] += 1
    
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
    
    remaining = [nid for nid, deg in in_degree.items() if deg > 0]
    
    if remaining:
        return result + [{"__cycle__": remaining}]
    return result