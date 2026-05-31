"""
Graph Parsers Module

Specialized parsers for each graph type:
- structural_parser: domains.csv, subdomains.csv, files.csv
- concerns_parser: domain_gaps/*.csv
- tasks_parser: file stubs, buggy components
- dependency_parser: AST source code analysis
"""

from pathlib import Path
import importlib.util

from .structural_parser import (
    parse_domains,
    parse_subdomains,
    parse_files,
    parse_structural_taxonomy
)

from .concerns_parser import (
    parse_domain_gap_csv,
    parse_all_domain_gaps,
    parse_concern_dependencies,
    extract_target_path,
    link_concerns_to_structural
)

from .tasks_parser import (
    create_implementation_tasks,
    parse_buggy_components,
    parse_all_buggy_components,
    calculate_priority
)

from .dependency_parser import (
    scan_source_modules,
    map_imports_to_taxonomy,
    register_file_dependencies,
    detect_cycles,
    topological_sort
)

# Import legacy parsers from parsers.py in graph/ directory
import importlib.util
_spec = importlib.util.spec_from_file_location("graph_parsers_legacy", Path(__file__).parent.parent / "parsers.py")
_legacy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_legacy)
parse_all_csvs = _legacy.parse_all_csvs
scan_modules = _legacy.scan_modules

__all__ = [
    # Structural
    "parse_domains",
    "parse_subdomains", 
    "parse_files",
    "parse_structural_taxonomy",
    # Concerns
    "parse_domain_gap_csv",
    "parse_all_domain_gaps",
    "parse_concern_dependencies",
    "extract_target_path",
    "link_concerns_to_structural",
    # Tasks
    "create_implementation_tasks",
    "parse_buggy_components",
    "parse_all_buggy_components",
    "calculate_priority",
    # Dependencies
    "scan_source_modules",
    "map_imports_to_taxonomy",
    "register_file_dependencies",
    "detect_cycles",
    "topological_sort",
    # Legacy compatibility
    "parse_all_csvs",
    "scan_modules"
]