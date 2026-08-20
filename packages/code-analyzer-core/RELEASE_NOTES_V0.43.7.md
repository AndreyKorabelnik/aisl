# code-analyzer-core 0.43.7

Version 0.43.7 adds structured workflow/configuration bindings to the canonical SQL analysis artifact.

## New canonical fact

`sql_workflow_binding` preserves scalar values observed in SQL-relevant YAML, JSON, properties, conf and shell configuration files.

Each fact contains:

- repository-relative file and exact line evidence;
- configuration path and local binding name;
- scalar value and value type;
- literal or template resolution status;
- referenced placeholders;
- portable provenance.

The extractor does not infer runtime substitution, deployment precedence or target-table semantics. It publishes observed configuration facts only.

## Why this is needed

SQL write targets can use placeholders such as `${$main_table_name}` while workflow YAML provides `main_table_name: epk_client`. Previously these observations existed in separate diagnostic outputs and could not be joined by the Knowledge Layer.

## Real repository result

On the unchanged `datamart_profile_fl` repository:

- 2,853 workflow/configuration scalar bindings were published;
- 2,406 are literal values;
- 447 contain templates;
- 15 exact `main_table_name` observations resolve to `epk_client` or `epk_client_v2`;
- 8 `sql.file` bindings and 44 pipeline-config-path bindings were preserved;
- the canonical artifact passed runner validation with repository-relative evidence only.
