# knowledge-layer-core 0.61.0a21

- Adds a scoped generic progress sink at the materialization runtime boundary and detailed phase timings for SQL analysis.
- Instruments SQL fact ingestion, workflow-context construction, target-lineage construction, validation, checkpoint, and publication without changing materialization API contracts.
- Prevents coarse file-level `s2tTableList` substitution when referenced placeholders have multiple observed values; scoped `name`/`prior_value` evidence remains responsible for those cases, avoiding cross-scope Cartesian producer edges.
- Aggregates equivalent workflow-target-lineage technical paths by terminal source relation/column plus effective non-passthrough transformation identity. Alternative projection/materialization paths remain provenance through counts, ID sets, and a deterministic representative path.
- Caches repeated workflow-reference template matching within one materialization and replaces row-by-row DuckDB `executemany` publication for workflow context with bounded multi-row inserts.
- Memoizes top-level producer output contracts while preserving path-sensitive recursive cycle handling.
- No Gold-specific, repository-specific, table-specific, or business-semantic rule was added.
