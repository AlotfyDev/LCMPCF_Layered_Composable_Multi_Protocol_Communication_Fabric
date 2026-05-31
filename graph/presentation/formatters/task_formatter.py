"""
Task formatters - Text output for task queries.
"""


def format_tasks_list(tasks: list) -> str:
    """Format tasks list for terminal output."""
    lines = ["Implementation Tasks", "=" * 20]

    priority_labels = {
        "critical": "CRITICAL",
        "high": "HIGH",
        "medium": "MEDIUM",
        "low": "LOW"
    }

    for t in tasks:
        priority = t.get("priority", "low").upper()
        task_id = t.get("id", "unknown")
        target = t.get("target_path", "N/A")
        concerns = t.get("required_concerns", [])
        concerns_str = f" [{', '.join(concerns)}]" if concerns else ""

        lines.append(f"[{priority}] {task_id}: {target}{concerns_str}")

    return "\n".join(lines)


def format_task_detail(task: dict) -> str:
    """Format a single task for terminal output."""
    lines = [f"Task: {task.get('id', 'unknown')}"]
    lines.append("-" * 40)
    lines.append(f"Target: {task.get('target_structural_id', 'N/A')}")
    lines.append(f"Path: {task.get('target_path', 'N/A')}")
    lines.append(f"Priority: {task.get('priority', 'N/A')}")
    lines.append(f"Status: {task.get('status', 'N/A')}")
    lines.append(f"Effort: {task.get('effort_estimate', 'N/A')}")

    if task.get("required_concerns"):
        lines.append(f"Concerns: {', '.join(task['required_concerns'])}")

    return "\n".join(lines)