import csv
import ast
import re
from pathlib import Path

SEVERITY_VALUES = {"critical", "high", "medium", "low", "vital"}
EFFORT_VALUES = {"xs", "s", "m", "l", "xl", "xxl", "3-7d"}
EFFORT_PATTERN = re.compile(r'^(\d+[-/]\d+[dhmw]?|xs|s|m|l|xl|xxl|\d+[dhmw])$', re.IGNORECASE)


def parse_all_csvs(csv_dirs):
    nodes = []
    for csv_dir in csv_dirs:
        d = Path(csv_dir)
        if not d.exists():
            continue
        for csv_file in sorted(d.glob("*.csv")):
            nodes.extend(parse_csv_file(csv_file))
    return nodes


def _repair_row(raw_row, headers):
    """Repair a malformed CSV row with extra fields due to unquoted commas."""
    expected = len(headers)
    if len(raw_row) <= expected:
        return raw_row

    is_buggy = "bug_type" in headers
    is_missing = "severity" in headers and "dependencies" in headers and "effort_estimate" in headers
    is_domain_gap = "category" in headers

    if is_domain_gap:
        return _merge_tail(raw_row, expected)
    elif is_buggy:
        return _repair_buggy(raw_row, expected)
    elif is_missing:
        result = _repair_missing(raw_row)
        if len(result) == expected:
            return result
        return _merge_tail(raw_row, expected)
    else:
        return _merge_tail(raw_row, expected)


def _merge_tail(raw_row, expected):
    """Merge extra fields into the last field."""
    result = list(raw_row)
    while len(result) > expected:
        last = result.pop()
        result[-1] = result[-1] + "," + last
    return result


def _find_severity_idx(fields, start):
    """Find index of a known severity keyword starting from `start`."""
    for i in range(start, len(fields)):
        val = fields[i].strip().lower().rstrip(".")
        if val in SEVERITY_VALUES:
            return i
    return None


def _find_effort_in_list(fields):
    """Find index of effort value, preferring later positions."""
    candidates = []
    for i, v in enumerate(fields):
        val = v.strip().lower()
        if val in EFFORT_VALUES or EFFORT_PATTERN.match(val):
            candidates.append(i)
    if not candidates:
        return None
    tail_candidates = [c for c in candidates if c >= len(fields) - 3 or c >= 1]
    if tail_candidates:
        return max(tail_candidates)
    return max(candidates)


def _repair_buggy(raw_row, expected):
    """Repair buggy_components rows using severity as anchor."""
    fields = list(raw_row)
    sev_idx = _find_severity_idx(fields, 5)
    if sev_idx is None:
        return _merge_tail(raw_row, expected)

    after_sev = fields[sev_idx + 1:]
    if not after_sev:
        result = list(fields[:sev_idx + 1]) + ["", ""]
    elif len(after_sev) == 1:
        result = list(fields[:sev_idx + 1]) + [after_sev[0], ""]
    else:
        result = list(fields[:sev_idx + 1]) + [",".join(after_sev[:-1]), after_sev[-1]]

    if len(result) != expected:
        return _merge_tail(raw_row, expected)
    return result


def _repair_missing(raw_row):
    """Repair missing_components rows using severity as anchor."""
    fields = list(raw_row)
    expected = 8

    sev_idx = _find_severity_idx(fields, 3)
    if sev_idx is None:
        return _merge_tail(raw_row, expected)

    result = list(fields[:3])
    desc = ",".join(fields[3:sev_idx])
    result.append(desc)
    result.append(fields[sev_idx])

    after = fields[sev_idx + 1:]
    if len(after) >= 3:
        eff_idx_in_after = _find_effort_in_list(after)
        if eff_idx_in_after is not None:
            result.append(",".join(after[:eff_idx_in_after]))
            result.append(after[eff_idx_in_after])
            result.append(",".join(after[eff_idx_in_after + 1:]))
            if len(result) == expected:
                return result
        result.append(",".join(after[:-2]))
        result.append(after[-2])
        result.append(after[-1])
    elif len(after) == 2:
        result.extend([after[0], after[1], ""])
    elif len(after) == 1:
        result.extend(["", after[0], ""])
    else:
        result.extend(["", "", ""])

    if len(result) == expected:
        return result
    return _merge_tail(raw_row, expected)


def parse_csv_file(filepath):
    nodes = []
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        headers = [h.strip() for h in next(reader) if h]

        for raw_row in reader:
            raw_row = _repair_row(raw_row, headers)
            row = dict(zip(headers, raw_row))
            row = {k.strip() if k else "": v.strip() if v else "" for k, v in row.items()}

            sev = row.get("severity", "")
            if sev:
                sev_lower = sev.lower()
                sev_map = {"vital": "high", "open": "open"}
                row["severity"] = sev_map.get(sev_lower, sev_lower)

            if "bug_type" in headers:
                node_type = "gap_buggy"
                subtype = row.get("bug_type", "")
                title = row.get("component", "")
                proposed_solution = row.get("proposed_fix", "")
                effort = ""
            elif "category" in headers:
                node_type = "gap_domain"
                subtype = row.get("category", "")
                title = row.get("title", "")
                proposed_solution = row.get("proposed_solution", "")
                effort = row.get("effort_estimate", "")
            else:
                node_type = "gap_missing"
                subtype = "missing_component"
                title = row.get("component", "")
                proposed_solution = row.get("proposed_solution", "")
                effort = row.get("effort_estimate", "")

            row_id = row.get("id", "")
            if not row_id:
                continue

            dep_ids = parse_dependencies(row.get("dependencies", ""))

            node = {
                "id": row_id, "type": node_type, "domain": row.get("domain", ""),
                "severity": row.get("severity", ""), "title": title,
                "description": row.get("description", ""), "effort": effort,
                "proposed_solution": proposed_solution,
                "file_path": row.get("file_path", ""), "dep_ids": dep_ids, "subtype": subtype,
            }
            nodes.append(node)
    return nodes


def parse_dependencies(raw):
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


def scan_modules(src_dir):
    src = Path(src_dir)
    nodes = []
    import_edges = []

    for py_file in sorted(src.rglob("*.py")):
        rel_path = py_file.relative_to(src).as_posix()

        if ".obsolete" in rel_path or ".obsoletes" in rel_path:
            continue

        try:
            with open(py_file, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read())
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    target = _resolve_module(alias.name, src)
                    if target:
                        import_edges.append((rel_path, target))
            elif isinstance(node, ast.ImportFrom):
                parts = []
                if node.level:
                    file_parts = rel_path.split("/")
                    base = file_parts[:-1]
                    for _ in range(node.level - 1):
                        if base:
                            base.pop()
                    parts = base
                if node.module:
                    parts += node.module.split(".")
                if parts:
                    full_module = ".".join(parts)
                    target = _resolve_module(full_module, src)
                    if target:
                        import_edges.append((rel_path, target))

        domain = rel_path.split("/")[0]
        nodes.append({
            "id": rel_path, "type": "module", "domain": domain,
            "severity": "N/A", "title": rel_path, "description": "",
            "effort": "", "proposed_solution": "",
            "file_path": str(py_file), "dep_ids": [], "subtype": "N/A",
        })

    return nodes, import_edges


def _resolve_module(name, src_dir):
    path = name.replace(".", "/")
    candidates = [src_dir / f"{path}.py", src_dir / path / "__init__.py"]
    for candidate in candidates:
        if candidate.exists():
            return candidate.relative_to(src_dir).as_posix()
    return None