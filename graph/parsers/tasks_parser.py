"""
Tasks Graph Parsers

Create work items from file stubs (implementation tasks) and buggy components (debug tasks).
"""
import csv
from pathlib import Path


def create_implementation_tasks(file_stubs: list[dict], concerns_lookup: dict) -> list[dict]:
    """Transform file_stub nodes into implementation tasks."""
    tasks = []
    
    for stub in file_stubs:
        task_id = f"Task_Impl_{stub['id']}"
        
        # Parse required concerns
        req_concerns = [c.strip() for c in stub.get("required_concerns", "").split(",") if c.strip()]
        
        # Derive priority from concern severity (highest wins)
        priority_order = {"critical": 3, "high": 2, "medium": 1, "low": 0}
        priority = "low"
        for cid in req_concerns:
            concern = concerns_lookup.get(cid, {})
            sev = concern.get("severity", "low").lower()
            if priority_order.get(sev, 0) >= priority_order.get(priority, 0):
                priority = sev
        
        # Get effort estimate from first concern
        effort = "S"
        if req_concerns:
            concern = concerns_lookup.get(req_concerns[0], {})
            effort = concern.get("effort_estimate", "S") or "S"
        
        tasks.append({
            "id": task_id,
            "node_type": "task_implement",
            "target_structural_id": stub["id"],
            "target_path": stub.get("path", ""),
            "priority": priority,
            "status": "not_started",
            "effort_estimate": effort,
            "required_concerns": req_concerns
        })
    
    return tasks


def parse_buggy_components(filepath: Path) -> list[dict]:
    """Parse buggy_components CSV into debug task objects."""
    tasks = []
    
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            tasks.append({
                "id": f"Task_Debug_{row['id'].strip()}",
                "node_type": "task_debug",
                "target_structural_id": row.get("component", "").strip(),
                "source_component_id": row["id"].strip(),
                "bug_type": row.get("bug_type", "").strip(),
                "severity": row.get("severity", "").strip(),
                "status": "not_started",
                "proposed_fix": row.get("proposed_fix", "").strip(),
                "evidence": row.get("evidence", "").strip()
            })
    
    return tasks


def parse_all_buggy_components(buggy_dir: Path) -> list[dict]:
    """Parse all buggy_components CSV files."""
    all_tasks = []
    if not buggy_dir.exists():
        return all_tasks
    
    for csv_file in sorted(buggy_dir.glob("*.csv")):
        all_tasks.extend(parse_buggy_components(csv_file))
    return all_tasks


def calculate_priority(concern_ids: list[str], concerns_lookup: dict) -> str:
    """Calculate task priority based on highest concern severity."""
    priority_order = {"critical": 3, "high": 2, "medium": 1, "low": 0}
    max_priority = "low"
    
    for cid in concern_ids:
        concern = concerns_lookup.get(cid, {})
        sev = concern.get("severity", "low").lower()
        if priority_order.get(sev, 0) > priority_order.get(max_priority, 0):
            max_priority = sev
    
    return max_priority