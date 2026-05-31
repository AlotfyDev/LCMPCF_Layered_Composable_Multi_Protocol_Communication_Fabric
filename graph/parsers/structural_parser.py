"""
Structural Graph Parsers

Parse domains.csv, subdomains.csv, and files.csv into the canonical structural taxonomy.
"""
import csv
from pathlib import Path


def parse_domains(filepath: Path) -> list[dict]:
    """Parse domains.csv into domain objects."""
    domains = []
    if not filepath.exists():
        return domains
    
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            domains.append({
                "id": row["element_number"].strip(),
                "name": row["element_name"].strip(),
            })
    return domains


def parse_subdomains(filepath: Path) -> list[dict]:
    """Parse subdomains.csv into subdomain objects."""
    subdomains = []
    if not filepath.exists():
        return subdomains
    
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            subdomains.append({
                "id": row["element_number"].strip(),
                "name": row["element_name"].strip(),
                "parent": row["parent_domain"].strip(),
            })
    return subdomains


def parse_files(filepath: Path) -> list[dict]:
    """Parse files.csv into file objects with parent extraction."""
    files = []
    if not filepath.exists():
        return files
    
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            elem_num = row["element_number"]
            
            # Extract parent from element_number
            if ".f" in elem_num:
                parts = elem_num.split(".f")[0].rsplit(".", 1)
                parent_id = parts[0] if len(parts) > 0 else None
            else:
                parent_id = None
            
            classification = row.get("classification", "Exists")
            files.append({
                "id": elem_num,
                "name": row["element_name"],
                "parent": parent_id,
                "path": row["full_path"],
                "node_type": "file_stub" if classification == "To_Be_Implemented" else "file",
                "classification": classification,
                "development_state": row.get("development_state", "production-grade"),
                "architectural_state": row.get("architectural_state", "current"),
                "required_concerns": row.get("required_concerns", "")
            })
    return files


def parse_structural_taxonomy(roadmap_dir: Path) -> tuple[list, list, list]:
    """Master function to parse all structural CSVs.
    
    Returns: (domains, subdomains, files)
    """
    domains = parse_domains(roadmap_dir / "domains.csv")
    subdomains = parse_subdomains(roadmap_dir / "subdomains.csv")
    files = parse_files(roadmap_dir / "files.csv")
    return domains, subdomains, files