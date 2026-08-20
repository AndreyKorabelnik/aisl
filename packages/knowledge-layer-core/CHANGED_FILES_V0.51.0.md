# Changed files — knowledge-layer-core 0.51.0

## Added

- `knowledge_layer_core/sql_relation_roles.py`
  - deterministic SQL relation role classification from read/write lifecycle and dependency evidence;
  - technical naming is only a supporting signal;
  - uncertain read-only staging sources remain visible.
- `sql_relation_semantic_role` typed table and index.
- focused semantic-role regression cases.

## Updated

- `knowledge_layer_core/sql_analysis_builder.py`
  - materializes relation roles after SQL fact ingestion.
- `knowledge_layer_core/sql_analysis_schema.py`
  - SQL schema version `knowledge_layer_sql/v2`.
- `knowledge_layer_core/query.py`
  - `business_sources`, `technical`, and `all` views;
  - relation classification fields and coverage.
- `README.md`, versions, validation expectations.
