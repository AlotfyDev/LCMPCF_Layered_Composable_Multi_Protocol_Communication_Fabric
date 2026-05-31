"""
Concerns Graph Parsers

Parse domain_gaps/*.csv into concern analysis objects and build relationships to structural nodes.
"""
import csv
import re
from pathlib import Path


def parse_domain_gap_csv(filepath: Path) -> list[dict]:
    """Parse a single domain_gaps CSV into concern objects."""
    concerns = []
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Handle None values from CSV
            def safe_get(key, default=""):
                val = row.get(key, default)
                return (val or default).strip()
            
            concern = {
                "id": safe_get("id"),
                "node_type": "concern",
                "domain": safe_get("domain"),
                "category": safe_get("category"),
                "title": safe_get("title"),
                "description": safe_get("description"),
                "severity": safe_get("severity"),
                "status": safe_get("status"),
                "impact": safe_get("impact"),
                "dependencies": safe_get("dependencies"),
                "effort_estimate": safe_get("effort_estimate"),
                "proposed_solution": safe_get("proposed_solution"),
                "evidence": safe_get("evidence"),
                "notes": safe_get("notes")
            }
            concerns.append(concern)
    return concerns


def parse_all_domain_gaps(domain_gaps_dir: Path) -> list[dict]:
    """Parse all CSV files in domain_gaps directory."""
    all_concerns = []
    if not domain_gaps_dir.exists():
        return all_concerns
    
    for csv_file in sorted(domain_gaps_dir.glob("*.csv")):
        all_concerns.extend(parse_domain_gap_csv(csv_file))
    return all_concerns


def parse_concern_dependencies(raw: str) -> list[str]:
    """Parse concern dependencies field into list of concern IDs."""
    if not raw or not raw.strip():
        return []
    
    tokens = []
    for part in raw.split(";"):
        for subpart in part.split(","):
            for token in subpart.strip().split():
                token = token.strip()
                if token and token.lower() != "none":
                    tokens.append(token)
    return tokens


def extract_target_path(concern: dict, structural_nodes: dict) -> list[str]:
    """Extract file paths from concern evidence/proposed_solution and match to structural nodes."""
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
    
    return list(set(matched_nodes))


def link_concerns_to_structural(concerns: list[dict], structural_nodes: dict) -> dict:
    """Create relationship edges between concerns and structural nodes.
    
    Returns dict with concern_id -> structural_ids mapping.
    """
    # Build lookup: required_concern -> structural node
    concern_to_structural = {}
    
    for tax_id, node in structural_nodes.items():
        if node["node_type"] in ("file", "file_stub"):
            req_concerns = node.get("required_concerns", "")
            if req_concerns:
                for concern in req_concerns.split(","):
                    concern = concern.strip()
                    if concern:
                        concern_to_structural.setdefault(concern, []).append(tax_id)
    
    # Link concerns to structural targets
    affects_edges = {}
    for concern in concerns:
        cid = concern["id"]
        # Get targets from required_concerns matching
        targets = concern_to_structural.get(cid, [])
        # Also check evidence
        targets.extend(extract_target_path(concern, structural_nodes))
        affects_edges[cid] = list(set(targets))
    
    return affects_edges