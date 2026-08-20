# knowledge-layer-core 0.57.0

## Observed storage usage and generic SQL materialization

- Added `observed-storage-usage/v1` as an independent KLC knowledge model.
- Registered `observed-storage-usage` and `sql-analysis` in `knowledge_materialization_runtime/v1`.
- Materialized observed reads, writes, access facts and explicit gaps without converting observations into declared-model facts.
- SQL materialization now consumes the generic Core `sql-analysis/v1` envelope and publishes the complete `common.sql*` capability set, including `common.sql-source-inventory`.
- No Task/Suite/Profile semantic selection or legacy fallback is used by either handler.
