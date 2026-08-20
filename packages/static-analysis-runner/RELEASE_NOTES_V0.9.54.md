# static-analysis-runner 0.9.54

## Legacy cleanup block 1 — runtime truth in the knowledge catalog

- Knowledge availability is now determined by actual registration in `knowledge_materialization_runtime/v1`, not by lifecycle-name whitelisting.
- `effective-data-model` and `workspace-sql-catalog` are correctly exposed as `current_typed` and executable through target contracts.
- Removed retired `common-data-model` from internal selection surfaces.
- Removed obsolete runtime-bridge descriptions for materializations already registered in the generic KLC runtime.
- No compatibility adapter, dual-write path or legacy fallback was added.
