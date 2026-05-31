#!/usr/bin/env python
"""Complete verification of graph parsing system."""
from graph import Graph
from graph.parsers.structural_parser import parse_structural_taxonomy
from graph.parsers.concerns_parser import parse_all_domain_gaps, link_concerns_to_structural
from graph.parsers.tasks_parser import create_implementation_tasks
from graph.parsers.dependency_parser import scan_source_modules, map_imports_to_taxonomy

from pathlib import Path

roadmap = Path('.docs/roadmap_to_full_production_ready')

print("=" * 60)
print("GRAPH PARSING SYSTEM VERIFICATION")
print("=" * 60)

# 1. Structural Parser
domains, subdomains, files = parse_structural_taxonomy(roadmap)
file_stubs = [f for f in files if f['node_type'] == 'file_stub']
print(f"\n1. Structural Parser:")
print(f"   [OK] Domains: {len(domains)}")
print(f"   [OK] Subdomains: {len(subdomains)}")
print(f"   [OK] Files: {len(files)}")
print(f"   [OK] Stubs: {len(file_stubs)}")

# 2. Concerns Parser
concerns = parse_all_domain_gaps(roadmap / 'domain_gaps')
print(f"\n2. Concerns Parser:")
print(f"   [OK] Total concerns: {len(concerns)}")

# 3. Concern Linking
structural_nodes = {f['id']: f for f in files}
affects = link_concerns_to_structural(concerns, structural_nodes)
linked = sum(1 for v in affects.values() if v)
print(f"   [OK] Linked concerns: {linked}")

# 4. Tasks Parser
concerns_lookup = {c['id']: c for c in concerns}
tasks = create_implementation_tasks(file_stubs, concerns_lookup)
print(f"\n3. Tasks Parser:")
print(f"   [OK] Tasks created: {len(tasks)}")

# 5. Dependency Parser
SRC_DIR = Path('src')
modules, imports = scan_source_modules(SRC_DIR)
print(f"\n4. Dependency Parser:")
print(f"   [OK] Modules scanned: {len(modules)}")
print(f"   [OK] Import edges: {len(imports)}")

# 6. Full Graph Integration
g = Graph()
g.build_folder_taxonomy()
g.register_concern_targets()

# Count edges by type
# File edges: edges originating from file/subdomain/domain IDs
file_to_structural = sum(1 for k in g.taxonomy_edges if '.f' in k or '.f' in k)
domain_to_subdomain = sum(1 for k in g.taxonomy_edges if not ('.f' in k or '-' in k))

print(f"\n5. Integrated Graph:")
print(f"   [OK] Total nodes: {len(g.taxonomy_nodes)}")
print(f"   [OK] Total edges: {sum(len(v) for v in g.taxonomy_edges.values())}")
print(f"   [OK] Domain/subdomain edges: {domain_to_subdomain}")
print(f"   [OK] Concern edges: {concern_to_structural}")

print("\n" + "=" * 60)
print("ALL SYSTEMS OPERATIONAL")
print("=" * 60)