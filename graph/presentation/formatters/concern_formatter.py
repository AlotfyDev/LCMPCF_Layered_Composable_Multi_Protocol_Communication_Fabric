"""
Concern formatters - Text output for concern queries.
"""


def format_concerns_list(concerns: list) -> str:
    """Format concerns list for terminal output."""
    lines = ["Concerns", "=" * 10]

    severity_icons = {
        "critical": "[!!!]",
        "high": "[!!]",
        "medium": "[!]",
        "low": "[ ]"
    }

    for c in concerns:
        icon = severity_icons.get(c.get("severity", "").lower(), "[ ]")
        lines.append(f"{icon} {c['id']}: {c.get('title', 'N/A')}")

    return "\n".join(lines)


def format_concern_detail(concern: dict) -> str:
    """Format a single concern for terminal output."""
    lines = [f"Concern: {concern.get('id', 'unknown')}"]
    lines.append("-" * 40)
    lines.append(f"Title: {concern.get('title', 'N/A')}")
    lines.append(f"Domain: {concern.get('domain', 'N/A')}")
    lines.append(f"Category: {concern.get('category', 'N/A')}")
    lines.append(f"Severity: {concern.get('severity', 'N/A')}")
    lines.append(f"Status: {concern.get('status', 'N/A')}")
    lines.append(f"Effort: {concern.get('effort_estimate', 'N/A')}")

    if concern.get("description"):
        lines.append("")
        lines.append("Description:")
        lines.append(concern.get("description", ""))

    if concern.get("dependencies"):
        lines.append("")
        lines.append(f"Dependencies: {concern.get('dependencies')}")

    if concern.get("proposed_solution"):
        lines.append("")
        lines.append("Proposed Solution:")
        lines.append(concern.get("proposed_solution", ""))

    return "\n".join(lines)