# knowledge-api 0.2.1 — physical table catalog restoration

## Fixed

`0.2.0` populated `field-catalog` only from annotation-based Java model objects. Relational systems such as AT900 store their table model in KLC `db_schema_table`/`db_schema_column`, so the endpoint returned `tables=[]` even when the Knowledge Layer contained physical tables.

`0.2.1` restores the unified former data-model-api behavior:

- physical SQL/DDL/jOOQ tables are returned as `table:<qualified_name>`;
- UCP logical objects remain available unchanged;
- physical detail maps columns, keys, declared FKs, observed joins, indexes, constraints, partitioning and triggers;
- no AT900-specific condition or system-name heuristic was added.

## Compatibility

Public paths and `data_model_api/v1` remain unchanged. This is a bug-fix release.
