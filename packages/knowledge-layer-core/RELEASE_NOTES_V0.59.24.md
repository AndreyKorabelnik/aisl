# knowledge-layer-core 0.59.24

## Change

Adds the typed read-side contract for the product SQL target-to-source mapping.

- `KnowledgeLayerQuery.list_sql_target_value_sources()` exposes `sql_target_value_source_mapping` and its explicit gaps without re-running lineage logic;
- capability discovery now exposes `common.sql-target-source-mapping` and `common.sql-target-value-source-mapping` whenever the materialized mart is present;
- target lookup accepts a qualified identifier and uses only its normalized logical table component for the existing workflow target identity;
- query output normalizes JSON evidence/provenance and provides deterministic pagination/status/gap summaries.

This is a read-only projection over already materialized KLC knowledge; no S2T inference moves into Knowledge API.
