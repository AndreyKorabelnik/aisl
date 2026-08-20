# knowledge-layer-core 0.52.5

Version 0.52.5 imports the canonical `sql_workflow_binding` stream produced by code-analyzer-core 0.43.7.

## Added

- typed `sql_workflow_binding` table;
- index by repository, binding name, status and file;
- capability `common.sql-workflow-bindings`;
- read-only `list_sql_workflow_bindings` query with filters and pagination.

## Evidence boundary

The Knowledge Layer preserves observed configuration values and provenance. It does not yet apply runtime precedence or propagate bindings through workflow-to-pipeline-to-SQL invocation chains. That deterministic context resolution is the next step.

## Real repository result

The unchanged `datamart_profile_fl` canonical SQL artifact was imported successfully:

- 2,853 workflow bindings;
- 47 `main_table_name` observations;
- 6 exact `epk_client` values;
- 9 exact `epk_client_v2` values;
- portable evidence preserved.
