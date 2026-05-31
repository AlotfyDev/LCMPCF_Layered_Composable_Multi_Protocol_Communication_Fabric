# Schema Matrix Cross-Reference

## Overview

This document maps the processing stages in `MappedSystemSchema.csv` to the actual node types and edge types in the system.

## Node Type Mappings

| Stage | Output Schema | Node Type(s) | Documentation |
|-------|--------------|--------------|---------------|
| 1-3 (Structural Load) | taxonomy_node/folder_domain | folder_domain | structural/graph_node_types/structural_graph.md |
| 1-3 (Structural Load) | taxonomy_node/folder_subdomain | folder_subdomain | structural/graph_node_types/structural_graph.md |
| 1-3 (Structural Load) | taxonomy_node/file | file, file_stub | structural/graph_node_types/structural_graph.md |
| 5 (Concerns Load) | concern_node | concern | concerns/graph_node_types/concerns_graph.md |
| 9-10 (Tasks Load) | task_node | task_implement | tasks/graph_node_types/tasks_graph.md |
| 9-10 (Tasks Load) | task_debug_node | task_debug | tasks/graph_node_types/tasks_graph.md |
| 7-8 (Dependencies) | module_node | module (internal) | dependency/graph_node_types/dependency_graph.md |

## Edge Type Mappings

| Stage | Edge Type | Source → Target | Documentation |
|-------|----------|----------------|---------------|
| 4 (Build Hierarchy) | parent_of | folder_domain → folder_subdomain | structural/graph_node_types/structural_graph.md |
| 4 (Build Hierarchy) | parent_of | folder_subdomain → file | structural/graph_node_types/structural_graph.md |
| 6 (Link Concerns) | affects | concern → file/file_stub | concerns/graph_node_types/concerns_graph.md |
| 8 (Register Imports) | imports | file → file | dependency/graph_node_types/dependency_graph.md |

## Schema Transition Diagram

```
CSV Files ──► Parse ──► Taxonomy Nodes ──► Concerns Link ──► Tasks Create ──► JSON Output
     │           │          │              │               │            │
     ▼           ▼          ▼              ▼               ▼            ▼
domains.csv   folder_    depth_chain    concern->        Task_Impl_    taxonomy_
subdomains.csv domain     added        file edges        file_stub     structure.json
files.csv     subdomain              affects edges
domain_gaps/  file/file_stub
*.csv
buggy_com-
ponents/*.csv
```

## Validation Matrix

| Input Schema | Validation Applied | Pass Condition |
|--------------|-----------------|----------------|
| csv/domains.csv | id present, name not empty | row valid |
| csv/subdomains.csv | id present, parent exists | row valid |
| csv/files.csv | id present, path valid | row valid |
| csv/domain_gaps/*.csv | id present, domain valid | row valid |
| python_modules/src/* | AST parses | file processed |

## Output Artifacts

| Artifact | Path | Contains |
|----------|------|----------|
| taxonomy_structure.json | .docs/taxonomy_structure.json | domains, subdomains, files, concerns, edges |
| concerns_edges | taxonomy_edges | concern -> structural relationships |
| dependency_edges | taxonomy_edges | file -> file imports |
| import_edges | internal | raw (path, path) tuples |

## Cross-System Dependencies

- Structural nodes feed Concerns linking (via `required_concerns`)
- Concerns feed Tasks (via severity for priority)
- Source modules feed Dependencies (via AST scanning)
- All feed the final JSON output