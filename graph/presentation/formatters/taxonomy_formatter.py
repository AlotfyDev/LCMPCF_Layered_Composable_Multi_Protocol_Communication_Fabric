"""
Taxonomy formatters - Text and diagram output for taxonomy queries.
"""


def format_taxonomy_summary(data: dict) -> str:
    """Format taxonomy summary for terminal output."""
    lines = ["Graph Taxonomy Summary", "=" * 30]

    by_type = data.get("by_type", {})
    lines.append(f"Domains: {by_type.get('folder_domain', 0)}")
    lines.append(f"Subdomains: {by_type.get('folder_subdomain', 0)}")
    lines.append(f"Files: {by_type.get('file', 0)}")
    lines.append(f"File Stubs: {by_type.get('file_stub', 0)}")

    lines.append("")
    lines.append("By Depth:")
    by_depth = data.get("by_depth", {})
    for depth in sorted(by_depth.keys()):
        lines.append(f"  Level {depth}: {by_depth[depth]}")

    return "\n".join(lines)


def format_node_detail(node: dict) -> str:
    """Format a single node for terminal output."""
    lines = [f"Node: {node.get('id', 'unknown')}"]
    lines.append("-" * 40)

    labels = {
        "folder_domain": "Domain",
        "folder_subdomain": "Subdomain",
        "file": "File",
        "file_stub": "File Stub",
        "concern": "Concern"
    }

    lines.append(f"Type: {labels.get(node.get('node_type', ''), node.get('node_type', 'unknown'))}")

    if node.get("depth_chain"):
        lines.append(f"Path: {' > '.join(node['depth_chain'])}")

    if node.get("node_type") in ("file", "file_stub"):
        lines.append(f"Path: {node.get('path', 'N/A')}")
        if node.get("required_concerns"):
            lines.append(f"Required Concerns: {node['required_concerns']}")

    if node.get("node_type") == "concern":
        lines.append(f"Title: {node.get('title', 'N/A')}")
        lines.append(f"Domain: {node.get('domain', 'N/A')}")
        lines.append(f"Severity: {node.get('severity', 'N/A')}")
        lines.append(f"Status: {node.get('status', 'N/A')}")

    return "\n".join(lines)


def format_mermaid_taxonomy(domains: list, subdomains: list, files: list) -> str:
    """Generate Mermaid diagram for taxonomy."""
    lines = ["graph TD"]
    lines.append('    subgraph LEGEND["Taxonomy Legend"]')
    lines.append('        domain["Domain (Level 1)"]')
    lines.append('        subdomain["Subdomain (Level 2)"]')
    lines.append('        file["File (Level 3)"]')
    lines.append('        stub["Stub (to implement)"]')
    lines.append('        concern["Concern"]')
    lines.append("    end")
    lines.append("")

    for domain in domains:
        domain_id = domain["id"].replace(".", "_")
        lines.append(f'    {domain_id}[\"{domain["name"]}\"]')

    for subdomain in subdomains:
        sub_id = subdomain["id"].replace(".", "_")
        parent_id = subdomain["parent"].replace(".", "_") if subdomain.get("parent") else None
        lines.append(f'    {sub_id}[\"{subdomain["name"]}\"]')
        if parent_id:
            lines.append(f"    {parent_id} --> {sub_id}")

    for f in files:
        file_id = f["id"].replace(".", "_")
        parent_id = f["parent"].replace(".", "_") if f.get("parent") else None
        icon = "(stub)" if f.get("node_type") == "file_stub" else ""
        lines.append(f'    {file_id}[\"{icon} {f["name"]}\"]')
        if parent_id:
            lines.append(f"    {parent_id} --> {file_id}")

    return "\n".join(lines)