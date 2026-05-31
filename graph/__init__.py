import json
from pathlib import Path

from .parsers import parse_all_csvs, scan_modules
from .parsers.structural_parser import parse_structural_taxonomy
from .parsers.concerns_parser import parse_all_domain_gaps, link_concerns_to_structural
from .parsers.tasks_parser import create_implementation_tasks, parse_all_buggy_components

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
SRC_DIR = PROJECT_ROOT / "src"
DOCS_DIR = PROJECT_ROOT / ".docs" / "roadmap_to_full_production_ready"
CSV_DIRS = [
    DOCS_DIR / "missing_components",
    DOCS_DIR / "buggy_components",
    DOCS_DIR / "domain_gaps",
]


class Graph:
    def __init__(self, nodes=None, edges=None, reverse=None):
        self.nodes = nodes if nodes is not None else {}
        self.edges = edges if edges is not None else {}
        self.reverse = reverse if reverse is not None else {}

    def _merge_node(self, existing, new):
        """Merge two nodes with the same ID, combining their information."""
        merged = dict(existing)
        for key, value in new.items():
            if value:
                existing_val = existing.get(key, "")
                # Prefer longer/more detailed values for text fields
                text_keys = {"description", "title", "proposed_solution"}
                if key in text_keys and len(value) > len(existing_val):
                    merged[key] = value
                elif not existing_val:
                    merged[key] = value
                # Combine lists
                if key == "dep_ids":
                    merged[key] = list(set(existing.get("dep_ids", []) + new.get("dep_ids", [])))
        return merged

    def build(self, src_dir=None, csv_dirs=None):
        src_dir = Path(src_dir or SRC_DIR)
        csv_dirs_list = csv_dirs or CSV_DIRS

        csv_nodes = parse_all_csvs(csv_dirs_list)
        for node in csv_nodes:
            nid = node["id"]
            if nid in self.nodes:
                self.nodes[nid] = self._merge_node(self.nodes[nid], node)
            else:
                self.nodes[nid] = node

        module_nodes, import_edges = scan_modules(src_dir)
        for node in module_nodes:
            nid = node["id"]
            if nid in self.nodes:
                self.nodes[nid] = self._merge_node(self.nodes[nid], node)
            else:
                self.nodes[nid] = node

        for from_id, to_id in import_edges:
            self._add_edge(from_id, to_id)

        self._module_to_node = self._build_module_index()
        for node in csv_nodes:
            for dep in node.get("dep_ids", []):
                self._try_match_dependency(node["id"], dep)

        for node in csv_nodes:
            fp = node.get("file_path", "")
            if fp:
                fp_norm = fp.replace("\\", "/").strip("/")
                if fp_norm.startswith("src/"):
                    fp_norm = fp_norm[4:]
                if fp_norm in self.nodes:
                    self._add_edge(node["id"], fp_norm)
                else:
                    for mid in list(self.nodes.keys()):
                        if self.nodes[mid]["type"] == "module" and fp_norm in mid:
                            self._add_edge(node["id"], mid)
                            break

    def _build_module_index(self):
        index = {}
        for nid, node in self.nodes.items():
            if node["type"] == "module":
                index[nid] = nid
                index[nid.replace(".py", "")] = nid
                title = node.get("title", "")
                if title and "/" in title:
                    parts = title.split("/")
                    if len(parts) > 1:
                        index[parts[-1].replace(".py", "")] = nid
        return index

    def _try_match_dependency(self, from_id, dep):
        if dep in self.nodes:
            self._add_edge(from_id, dep)
            return True
        dep_path = dep.replace(".", "/")
        for mid in self._module_to_node:
            if dep_path == mid or dep_path.replace("\\", "/") == mid:
                self._add_edge(from_id, self._module_to_node[mid])
                return True
        for mid in self.nodes:
            if self.nodes[mid]["type"] == "module":
                if dep_path in mid or mid.replace(".py", "") in dep_path:
                    self._add_edge(from_id, mid)
                    return True
        return False

    def _add_edge(self, from_id, to_id):
        if from_id not in self.edges:
            self.edges[from_id] = set()
        self.edges[from_id].add(to_id)
        if to_id not in self.reverse:
            self.reverse[to_id] = set()
        self.reverse[to_id].add(from_id)

    def get_node(self, id):
        return self.nodes.get(id)

    def get_dependencies(self, id):
        deps = self.edges.get(id, set())
        return [self.nodes.get(d) for d in deps if d in self.nodes]

    def get_dependents(self, id):
        deps = self.reverse.get(id, set())
        return [self.nodes.get(d) for d in deps if d in self.nodes]

    def detect_cycles(self, domain=None):
        if domain:
            relevant = {nid for nid, n in self.nodes.items() if n["domain"] == domain}
        else:
            relevant = set(self.nodes.keys())
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {nid: WHITE for nid in relevant}
        parent = {}
        cycles = []
        def dfs(nid):
            color[nid] = GRAY
            for dep_id in self.edges.get(nid, set()):
                if dep_id not in relevant:
                    continue
                if color[dep_id] == GRAY:
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
        for nid in relevant:
            if color[nid] == WHITE:
                dfs(nid)
        return cycles

    def topological_sort(self, domain=None):
        if domain:
            relevant = {nid for nid, n in self.nodes.items() if n["domain"] == domain}
        else:
            relevant = set(self.nodes.keys())
        in_degree = {nid: 0 for nid in relevant}
        for from_id, to_ids in self.edges.items():
            if from_id in relevant:
                for to_id in to_ids:
                    if to_id in relevant:
                        in_degree[to_id] = in_degree.get(to_id, 0) + 1
        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        result = []
        while queue:
            node = queue.pop(0)
            result.append(node)
            for dep_id in self.edges.get(node, set()):
                if dep_id in in_degree:
                    in_degree[dep_id] -= 1
                    if in_degree[dep_id] == 0:
                        queue.append(dep_id)
        remaining = [nid for nid, deg in in_degree.items() if deg > 0]
        if remaining:
            cycles = self.detect_cycles(domain)
            result.append({"__cycle__": remaining, "cycles": cycles})
        return result

    def impact_analysis(self, id, depth=3):
        result = {"root": id, "levels": {}}
        visited = set()
        def _collect(current, level):
            if level > depth or current in visited:
                return
            visited.add(current)
            if level not in result["levels"]:
                result["levels"][level] = []
            node = self.nodes.get(current)
            if node:
                result["levels"][level].append(node)
            for dep in self.reverse.get(current, set()):
                _collect(dep, level + 1)
        _collect(id, 0)
        return result

    def get_all_by_severity(self, severity):
        return [n for n in self.nodes.values() if n["severity"].lower() == severity.lower()]

    def get_all_by_domain(self, domain):
        return [n for n in self.nodes.values() if n["domain"] == domain]

    def get_critical_path(self):
        critical_ids = {
            nid for nid, n in self.nodes.items()
            if n["severity"].lower() in ("critical", "high")
        }
        visited = set()
        def walk(nid):
            if nid in visited or nid not in self.nodes:
                return []
            visited.add(nid)
            deps = self.reverse.get(nid, set()) & critical_ids
            longest = []
            for dep in deps:
                sub = walk(dep)
                if len(sub) > len(longest):
                    longest = sub
            return [nid] + longest
        chain = []
        for nid in critical_ids:
            path = walk(nid)
            if len(path) > len(chain):
                chain = path
        return chain

    def summary(self):
        by_type = {}
        by_severity = {}
        by_domain = {}
        for n in self.nodes.values():
            by_type[n["type"]] = by_type.get(n["type"], 0) + 1
            sev = n["severity"].lower() if n["severity"] != "N/A" else "n/a"
            by_severity[sev] = by_severity.get(sev, 0) + 1
            dom = n["domain"] if n["domain"] else "unknown"
            by_domain[dom] = by_domain.get(dom, 0) + 1
        impact_scores = []
        for nid in self.nodes:
            dep_count = len(self.reverse.get(nid, set()))
            impact_scores.append((nid, dep_count))
        impact_scores.sort(key=lambda x: -x[1])
        top_10 = [(nid, c) for nid, c in impact_scores[:10] if c > 0]
        crit_path = self.get_critical_path()
        return {
            "total_nodes": len(self.nodes),
            "total_edges": sum(len(v) for v in self.edges.values()),
            "by_type": by_type,
            "by_severity": by_severity,
            "by_domain": by_domain,
            "top_10_impact": top_10,
            "critical_path": crit_path,
        }

    def save(self, path="graph_export.json"):
        data = {
            "nodes": self.nodes,
            "edges": {k: list(v) for k, v in self.edges.items()},
            "reverse": {k: list(v) for k, v in self.reverse.items()},
        }
        filepath = Path(path)
        if not filepath.is_absolute():
            filepath = HERE / filepath
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return str(filepath)

    def load(self, path):
        filepath = Path(path)
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.nodes = data["nodes"]
        self.edges = {k: set(v) for k, v in data.get("edges", {}).items()}
        self.reverse = {k: set(v) for k, v in data.get("reverse", {}).items()}

    def build_taxonomy(self):
        taxonomy = {
            "system_name": "Multi-Protocol Communication Fabric",
            "primary_taxonomy": {
                "L3_network": {"description": "Connection pooling, load balancing, circuit breaking, routing", "nodes": []},
                "L4_transport": {"description": "Reliable byte transfer, connection state, retry logic, framing", "nodes": []},
                "L5_session": {"description": "Session lifecycle, checkpointing, dispatcher, coordinator", "nodes": []},
                "L6_presentation": {"description": "Serialization, streaming codecs, compression, content negotiation", "nodes": []},
                "L7_protocols": {"description": "Protocol-specific framing, headers, error mapping, negotiation", "nodes": []},
            },
            "cross_cutting_domains": {
                "security": {"description": "TLS/mTLS, encryption, authentication", "nodes": []},
                "observability": {"description": "Metrics, logging, tracing, monitoring", "nodes": []},
                "testing": {"description": "Unit tests, integration tests, test infrastructure", "nodes": []},
                "devops": {"description": "Docker, CI/CD, configuration, deployment", "nodes": []},
                "wiring_di": {"description": "Composition root, dependency injection, factory pattern", "nodes": []},
                "gateway_sdk": {"description": "Edge adapters, remote gateways, client SDKs", "nodes": []},
            },
            "layer_statistics": {}
        }
        domain_mapping = {
            "network_L3": "L3_network", "transport_L4": "L4_transport",
            "session_L5": "L5_session", "presentation_L6": "L6_presentation",
            "protocols_L7": "L7_protocols",
        }
        for nid, node in self.nodes.items():
            if node["type"] in ("gap_domain", "gap_missing", "gap_buggy"):
                domain = node["domain"]
                if domain in domain_mapping:
                    taxonomy["primary_taxonomy"][domain_mapping[domain]]["nodes"].append({
                        "id": nid, "severity": node.get("severity", "unknown"),
                        "title": node.get("title", ""), "category": node.get("category", ""),
                    })
                elif domain in taxonomy["cross_cutting_domains"]:
                    taxonomy["cross_cutting_domains"][domain]["nodes"].append({
                        "id": nid, "severity": node.get("severity", "unknown"),
                        "title": node.get("title", ""), "category": node.get("category", ""),
                    })
        for layer, data in taxonomy["primary_taxonomy"].items():
            severities = [n["severity"] for n in data["nodes"]]
            taxonomy["layer_statistics"][layer] = {
                "total": len(data["nodes"]),
                "by_severity": {"critical": severities.count("critical"), "high": severities.count("high"),
                               "medium": severities.count("medium"), "low": severities.count("low")}
            }
        return taxonomy

    def load_taxonomy_csvs(self, roadmap_dir=None):
        """Load domains, subdomains, and files CSVs to build folder taxonomy graph."""
        import csv
        from pathlib import Path
        
        roadmap = Path(roadmap_dir or DOCS_DIR)
        
        # Parse domains.csv for root-level domain folders
        domains = []
        domains_file = roadmap / "domains.csv"
        if domains_file.exists():
            with open(domains_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    domains.append({
                        "id": row["element_number"],
                        "name": row["element_name"],
                    })
        
        # Parse subdomains.csv for subdomain folders
        subdomains = []
        subdomains_file = roadmap / "subdomains.csv"
        if subdomains_file.exists():
            with open(subdomains_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    subdomains.append({
                        "id": row["element_number"],
                        "name": row["element_name"],
                        "parent": row["parent_domain"],
                    })
        
        # Parse files.csv for file nodes
        files = []
        files_file = roadmap / "files.csv"
        if files_file.exists():
            with open(files_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Extract parent folder from element_number
                    # e.g., "0.1.1.1.f" -> parent "0.1.1" (adapters)
                    elem_num = row["element_number"]
                    if ".f" in elem_num:
                        parts = elem_num.split(".f")[0].rsplit(".", 1)
                        parent_id = parts[0] if len(parts) > 0 else None
                        file_depth = len(elem_num.split(".f")[0].split("."))
                    else:
                        parent_id = elem_num
                        file_depth = len(elem_num.split("."))
                    
                    files.append({
                        "id": elem_num,
                        "name": row["element_name"],
                        "parent": parent_id,
                        "path": row["full_path"],
                        "classification": row.get("classification", "Exists"),
                        "development_state": row.get("development_state", "production-grade"),
                        "architectural_state": row.get("architectural_state", "current"),
                        "required_concerns": row.get("required_concerns", "")
                    })

        return domains, subdomains, files

    def load_cross_cutting_concerns(self, roadmap_dir=None):
        """Load concerns from domain_gaps CSVs for cross-cutting graph."""
        import csv
        from pathlib import Path

        roadmap = Path(roadmap_dir or DOCS_DIR)
        concerns = []
        domain_gaps_dir = roadmap / "domain_gaps"

        if domain_gaps_dir.exists():
            for csv_file in sorted(domain_gaps_dir.glob("*.csv")):
                with open(csv_file, "r", encoding="utf-8-sig") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        concern = {
                            "id": row["id"],
                            "node_type": "concern",
                            "domain": row["domain"],  # security, observability, testing, etc.
                            "category": row.get("category", ""),
                            "title": row.get("title", ""),
                            "description": row.get("description", ""),
                            "severity": row.get("severity", ""),
                            "status": row.get("status", ""),
                            "impact": row.get("impact", ""),
                            "dependencies": row.get("dependencies", ""),
                            "effort_estimate": row.get("effort_estimate", ""),
                            "proposed_solution": row.get("proposed_solution", ""),
                            "evidence": row.get("evidence", ""),
                            "notes": row.get("notes", "")
                        }
                        concerns.append(concern)

        return concerns

    def register_concern_targets(self):
        """Link concerns to structural nodes via required_concerns attribute."""
        from .parsers.concerns_parser import link_concerns_to_structural
        
        self.taxonomy_nodes = getattr(self, 'taxonomy_nodes', {})
        
        # Build concerns list from taxonomy_nodes (already loaded as concern nodes)
        concerns = [
            node for node in self.taxonomy_nodes.values() 
            if node.get("node_type") == "concern"
        ]
        
        # Use the parser to create affects relationships
        affects_edges = link_concerns_to_structural(concerns, self.taxonomy_nodes)
        
        # Add edges to taxonomy_edges
        for concern_id, structural_ids in affects_edges.items():
            for sid in structural_ids:
                self._add_taxonomy_edge(concern_id, sid)
        
        return self

    def build_folder_taxonomy(self, roadmap_dir=None):
        """Build hierarchical graph from CSV taxonomy data with depth_chain and ancestors_chain."""
        domains, subdomains, files = self.load_taxonomy_csvs(roadmap_dir)
        
        # Build domain lookup for chain resolution
        domain_lookup = {d["id"]: d["name"] for d in domains}
        
        def get_depth_chain(node_id, node_type):
            """Build chain of ancestry from root domain to this node."""
            if node_type == "folder_domain":
                return [node_id]
            elif node_type == "folder_subdomain":
                parent = None
                for s in subdomains:
                    if s["id"] == node_id:
                        parent = s["parent"]
                        break
                if parent:
                    return get_depth_chain(parent, "folder_domain") + [node_id]
                return [node_id]
            else:  # file
                parent = None
                for f in files:
                    if f["id"] == node_id:
                        parent = f["parent"]
                        break
                if parent:
                    return get_depth_chain(parent, "folder_subdomain") + [node_id]
                return [node_id]
        
        def get_ancestors_chain(node_id):
            """Build chain from node back to root (reverse of depth_chain)."""
            chain = get_depth_chain(node_id, "file" if ".f" in node_id else "folder_subdomain" if "." in node_id else "folder_domain")
            return list(reversed(chain))
        
        # Add all taxonomy nodes with both chains
        for domain in domains:
            self.taxonomy_nodes = getattr(self, 'taxonomy_nodes', {})
            self.taxonomy_nodes[domain["id"]] = {
                "id": domain["id"],
                "name": domain["name"],
                "parent": None,
                "depth": 1,
                "node_type": "folder_domain",
                "depth_chain": get_depth_chain(domain["id"], "folder_domain"),
                "ancestors_chain": get_ancestors_chain(domain["id"])
            }
        
        for subdomain in subdomains:
            self.taxonomy_nodes = getattr(self, 'taxonomy_nodes', {})
            self.taxonomy_nodes[subdomain["id"]] = {
                "id": subdomain["id"],
                "name": subdomain["name"],
                "parent": subdomain["parent"],
                "depth": 2,
                "node_type": "folder_subdomain",
                "depth_chain": get_depth_chain(subdomain["id"], "folder_subdomain"),
                "ancestors_chain": get_ancestors_chain(subdomain["id"])
            }
            self._add_taxonomy_edge(subdomain["parent"], subdomain["id"])
        
        for file_node in files:
            self.taxonomy_nodes = getattr(self, 'taxonomy_nodes', {})
            # Differentiate file vs file_stub based on classification
            node_type = "file_stub" if file_node.get("classification") == "To_Be_Implemented" else "file"
            self.taxonomy_nodes[file_node["id"]] = {
                "id": file_node["id"],
                "name": file_node["name"],
                "parent": file_node["parent"],
                "depth": 3,
                "node_type": node_type,
                "path": file_node["path"],
                "classification": file_node.get("classification", "Exists"),
                "development_state": file_node.get("development_state", "production-grade"),
                "architectural_state": file_node.get("architectural_state", "current"),
                "required_concerns": file_node.get("required_concerns", ""),
                "depth_chain": get_depth_chain(file_node["id"], "file"),
                "ancestors_chain": get_ancestors_chain(file_node["id"]),
                "depends_on": [],      # Files this file imports/depends on
                "depended_by": []       # Files that import/depend on this file
            }
            self._add_taxonomy_edge(file_node["parent"], file_node["id"])

        # Add cross-cutting concern nodes
        for concern in self.load_cross_cutting_concerns():
            self.taxonomy_nodes = getattr(self, 'taxonomy_nodes', {})
            self.taxonomy_nodes[concern["id"]] = {
                "id": concern["id"],
                "node_type": "concern",
                "domain": concern["domain"],
                "category": concern["category"],
                "title": concern["title"],
                "description": concern["description"],
                "severity": concern["severity"],
                "status": concern["status"],
                "impact": concern["impact"],
                "dependencies": concern["dependencies"],
                "effort_estimate": concern["effort_estimate"],
                "proposed_solution": concern["proposed_solution"],
                "evidence": concern["evidence"],
                "notes": concern["notes"],
                "depth": 1,  # Concerns at root level
                "parent": None,
                "depth_chain": [concern["id"]],
                "ancestors_chain": [concern["id"]]
            }

        return self
    
    def _add_taxonomy_edge(self, from_id, to_id):
        """Add edge to taxonomy_edges dict."""
        self.taxonomy_edges = getattr(self, 'taxonomy_edges', {})
        self.taxonomy_edges[from_id] = self.taxonomy_edges.get(from_id, set()) | {to_id}
    
    def taxonomy_summary(self):
        """Get summary stats for taxonomy nodes only."""
        self.taxonomy_nodes = getattr(self, 'taxonomy_nodes', {})
        self.taxonomy_edges = getattr(self, 'taxonomy_edges', {})
        
        by_type = {}
        by_depth = {}
        
        for n in self.taxonomy_nodes.values():
            node_type = n["node_type"]
            by_type[node_type] = by_type.get(node_type, 0) + 1
            depth = n["depth"]
            by_depth[depth] = by_depth.get(depth, 0) + 1
        
        return {
            "total_nodes": len(self.taxonomy_nodes),
            "total_edges": sum(len(v) for v in self.taxonomy_edges.values()),
            "by_type": by_type,
            "by_depth": by_depth
        }
    
    def save_taxonomy_json(self, path=".docs/taxonomy_structure.json"):
        """Save the taxonomy structure as JSON with dependency info."""
        self.taxonomy_nodes = getattr(self, 'taxonomy_nodes', {})
        self.taxonomy_edges = getattr(self, 'taxonomy_edges', {})

        domains = [n for n in self.taxonomy_nodes.values() if n["node_type"] == "folder_domain"]
        subdomains = [n for n in self.taxonomy_nodes.values() if n["node_type"] == "folder_subdomain"]
        files = [n for n in self.taxonomy_nodes.values() if n["node_type"] in ("file", "file_stub")]
        concerns = [n for n in self.taxonomy_nodes.values() if n["node_type"] == "concern"]

        data = {
            "domains": domains,
            "subdomains": subdomains,
            "files": files,
            "concerns": concerns,
            "total_nodes": len(self.taxonomy_nodes),
            "total_edges": sum(len(v) for v in self.taxonomy_edges.values()),
            "dependency_edges": {
                k: list(v) for k, v in self.taxonomy_edges.items()
                if k is not None and any(v)
            }
        }

        filepath = Path(path)
        if not filepath.is_absolute():
            filepath = PROJECT_ROOT / filepath
        filepath.parent.mkdir(parents=True, exist_ok=True)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return str(filepath)

    def register_taxonomy_dependencies(self):
        """Scan module imports and register dependencies between taxonomy files."""
        self.taxonomy_nodes = getattr(self, 'taxonomy_nodes', {})
        
        # First scan all modules to build import edges
        module_nodes, import_edges = scan_modules(SRC_DIR)
        
        # Build lookup: file_path -> taxonomy node id
        path_to_taxonomy_id = {}
        for tax_id, tax_node in self.taxonomy_nodes.items():
            if tax_node["node_type"] == "file":
                path_to_taxonomy_id[tax_node["path"]] = tax_id
        
        # Process import edges - map to taxonomy IDs
        for from_path, to_path in import_edges:
            from_tax_id = path_to_taxonomy_id.get(from_path)
            to_tax_id = path_to_taxonomy_id.get(to_path)
            
            if from_tax_id and to_tax_id:
                # Add to depends_on for from node
                if "depends_on" not in self.taxonomy_nodes[from_tax_id]:
                    self.taxonomy_nodes[from_tax_id]["depends_on"] = []
                self.taxonomy_nodes[from_tax_id]["depends_on"].append(to_tax_id)
                
                # Add to depended_by for to node
                if "depended_by" not in self.taxonomy_nodes[to_tax_id]:
                    self.taxonomy_nodes[to_tax_id]["depended_by"] = []
                self.taxonomy_nodes[to_tax_id]["depended_by"].append(from_tax_id)
        
        return self
    
    def get_files_by_domain(self, domain_id):
        """Get all files within a specific domain (including stubs)."""
        self.taxonomy_nodes = getattr(self, 'taxonomy_nodes', {})
        return [
            node for node in self.taxonomy_nodes.values()
            if node["node_type"] in ("file", "file_stub") and node["ancestors_chain"][-1].startswith(domain_id)
        ]
    
    def analyze_domain_dependencies(self, domain_id):
        """Analyze dependency relationships within a single domain."""
        self.taxonomy_nodes = getattr(self, 'taxonomy_nodes', {})
        
        domain_files = self.get_files_by_domain(domain_id)
        domain_file_ids = {f["id"] for f in domain_files}
        
        # Internal dependencies (within domain)
        internal_deps = {}
        external_deps = {}
        
        for file_node in domain_files:
            fid = file_node["id"]
            # Internal deps: both source and target are in this domain
            internal = [d for d in file_node.get("depends_on", []) if d in domain_file_ids]
            # External deps: target is outside this domain
            external = [d for d in file_node.get("depends_on", []) if d not in domain_file_ids]
            
            if internal:
                internal_deps[fid] = internal
            if external:
                external_deps[fid] = external
        
        return {
            "domain_id": domain_id,
            "total_files": len(domain_files),
            "internal_dependencies": internal_deps,
            "external_dependencies": external_deps
        }
    
    def build_dependency_registry(self):
        """Build formal dependency registry with relationship node types."""
        self.taxonomy_nodes = getattr(self, 'taxonomy_nodes', {})
        self.dependency_registry = getattr(self, 'dependency_registry', [])
        
        # Create relationship entries for each dependency
        for tax_id, node in self.taxonomy_nodes.items():
            if node["node_type"] != "file":
                continue
            
            for dep_id in node.get("depends_on", []):
                relationship = {
                    "id": f"rel_{tax_id}_depends_{dep_id}",
                    "type": "dependency",
                    "source": tax_id,
                    "target": dep_id,
                    "relationship_type": "imports",
                    "source_path": node["path"],
                    "target_path": self.taxonomy_nodes[dep_id]["path"] if dep_id in self.taxonomy_nodes else None
                }
                self.dependency_registry.append(relationship)

        return self

    def build_mermaid_folder_taxonomy(self):
        """Generate Mermaid diagram from folder taxonomy structure."""
        self.taxonomy_nodes = getattr(self, 'taxonomy_nodes', {})
        self.taxonomy_edges = getattr(self, 'taxonomy_edges', {})

        lines = ["graph TD"]

        # Group by depth level
        domains = sorted([n for n in self.taxonomy_nodes.values() if n["node_type"] == "folder_domain"],
                         key=lambda x: x["id"])
        subdomains = sorted([n for n in self.taxonomy_nodes.values() if n["node_type"] == "folder_subdomain"],
                          key=lambda x: x["id"])
        files = sorted([n for n in self.taxonomy_nodes.values() if n["node_type"] in ("file", "file_stub")],
                      key=lambda x: x["id"])

        # Create subgraph for each domain folder
        for domain in domains:
            domain_id = domain["id"]
            domain_name = domain["name"]
            safe_id = domain_id.replace(".", "_")

            lines.append(f"    subgraph {safe_id} [\"{domain_name}\"]")

            # Add subdomain nodes
            domain_subs = [s for s in subdomains if s["parent"] == domain_id]
            for sub in domain_subs:
                sub_id = sub["id"].replace(".", "_")
                lines.append(f'        {sub_id}["{sub["name"]}"]')

            # Add file nodes in this domain (files directly under domain)
            domain_files = [f for f in files if f["parent"] == domain_id]
            for file_node in domain_files:
                file_id = file_node["id"].replace(".", "_")
                icon = "file" if file_node["node_type"] == "file" else "stub"
                lines.append(f'        {file_id}["{icon}: {file_node["name"]}"]')

            lines.append("    end")

        # Add edges: parent -> child
        for parent_id, children in self.taxonomy_edges.items():
            if parent_id is None:
                continue
            safe_parent = parent_id.replace(".", "_")
            for child_id in sorted(children):
                safe_child = child_id.replace(".", "_")
                lines.append(f"    {safe_parent} --> {safe_child}")

        return "\n".join(lines)

    def build_mermaid_taxonomy(self):
        lines = ["graph TD"]
        lines.append("    subgraph LAYERS [\"OSI Layers\"]")
        layers = ["L3_network", "L4_transport", "L5_session", "L6_presentation", "L7_protocols"]
        layer_domains = {"L3_network": "network_L3", "L4_transport": "transport_L4", "L5_session": "session_L5",
                         "L6_presentation": "presentation_L6", "L7_protocols": "protocols_L7"}
        layer_labels = {
            "L3_network": "Network (L3)",
            "L4_transport": "Transport (L4)",
            "L5_session": "Session (L5)",
            "L6_presentation": "Presentation (L6)",
            "L7_protocols": "Protocols (L7)",
        }
        for layer in layers:
            count = sum(1 for n in self.nodes.values() if n["domain"] == layer_domains[layer])
            label = layer_labels[layer]
            lines.append(f'        {layer}["{label} - {count}"]')
        lines.append("    end")
        lines.append('    subgraph CROSS_CUTTING ["Cross-Cutting"]')
        cross_domains = ["security", "observability", "testing", "devops", "wiring_di", "gateway_sdk"]
        for domain in cross_domains:
            count = sum(1 for n in self.nodes.values() if n["domain"] == domain)
            if count > 0:
                lines.append(f'        {domain}["{domain} - {count}"]')
        lines.append("    end")
        lines.append('    L3_network --> L4_transport')
        lines.append('    L4_transport --> L5_session')
        lines.append('    L5_session --> L6_presentation')
        lines.append('    L6_presentation --> L7_protocols')
        return "\n".join(lines)


graph = Graph()
graph.build()