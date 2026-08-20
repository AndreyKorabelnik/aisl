# knowledge-layer-core 0.58.1

## Legacy cleanup block 1 — canonical materialization catalog

- Removed the retired `common-data-model` umbrella from the current materialization catalog.
- Removed the duplicate planned `workspace-sql-mart-catalog`; the current `workspace-sql-catalog` runtime is the single workspace SQL composition contract.
- Materialization counts are derived from actual registered runtime handlers instead of stale constants.
- The current catalog now contains 14 materializations, 7 registered generic runtime handlers and 2 remaining planned migrations.
- No compatibility adapter, dual-write path or legacy fallback was added.
