# Pipeline Schema Matrix Headers

## Unified Header Structure

All pipeline schema CSV files use the same header structure:

| Column | Description | Example |
|--------|-------------|---------|
| `stage_order` | Processing step number (1, 2, 3...) | `1` |
| `stage_name` | Human-readable stage name | `"Load Domains"` |
| `input_schema_type` | Schema type identifier | `"csv/domains.csv"` |
| `input_format` | Format of input data | `"csv"`, `"json"`, `"python_module"` |
| `output_schema_type` | Schema type identifier for output | `"taxonomy_node/domain"` |
| `output_format` | Format of output data | `"dict"`, `"json_array"` |
| `processing_logic` | Brief description of transformation | `"Parse domain_number,name into node"` |
| `input_location` | File path pattern | `.docs/roadmap_to_full_production_ready/domains.csv` |
| `output_location` | Where output is stored | `taxonomy_nodes[0.1]` |
| `schema_template_ref` | Reference to detailed schema | `structural/node_types/domain.md` |
| `validation_rules` | Data validation applied | `"required: id,name"` |

## Schema Reference Format

`schema_template_ref` uses path notation:
- `{graph_type}/node_types/{type_name}.md` - Node type schema
- `{graph_type}/schemas/{artifact}.json` - JSON schema artifact
- `{graph_type}/pipeline/{stage}_schema.json` - Pipeline stage schema

## Processing Logic Notation

Use verb-noun format:
- `parse`, `validate`, `transform`, `merge`, `filter`, `register`, `link`, `build`, `save`, `detect`, `sort`

## Example Row

```csv
stage_order,stage_name,input_schema_type,input_format,output_schema_type,output_format,processing_logic,input_location,output_location,schema_template_ref,validation_rules
1,Load Domains,csv/domains.csv,csv,taxonomy_node/domain,dict,parse element_number->id, element_name->name,element_number into node,.docs/roadmap_to_full_production_ready/domains.csv,taxonomy_nodes[id],structural_graph/node_types/structural_graph.md,"required: id, element_number not null"
```