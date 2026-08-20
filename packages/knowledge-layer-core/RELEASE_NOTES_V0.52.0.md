# knowledge-layer-core 0.52.0

## SQL Source Inventory v1 export

- Added deterministic relation and field evidence summaries:
  - `evidence_count`;
  - `evidence_count_by_role`;
  - bounded `evidence_refs` with occurrence IDs, statement and scope IDs;
  - `evidence_truncated`.
- Added `max_evidence_per_role` to `list_sql_relations`.
- Added `export_sql_source_inventory` for a complete inventory without manual pagination.
- Added `write_sql_source_inventory_jsonl` with stable `sql-source-inventory/v1` records and SHA-256.
- Added capability `common.sql-source-inventory-export`.

The export contains deterministic SQL/KLC facts only. It does not include LLM interpretations
or infer owners for unresolved column usages.
