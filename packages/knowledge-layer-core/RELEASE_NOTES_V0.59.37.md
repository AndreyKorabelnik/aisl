# knowledge-layer-core 0.59.37

## Repository/workspace code-declared model read surface

- Exposes observed type and field annotations from already materialized `code-declared-data-model/v1` knowledge.
- Adds `summarize_code_declared_model` with exact annotation filters and field-exclusion filters supplied by the consumer.
- Adds relationship cardinality hints with explicit basis derived from declared Java container structure.
- Preserves raw declarations and provenance; semantic projection is opt-in and does not erase ignored declarations.
- Supports repository-scoped and workspace-scoped reads with the same query service.
- Does not hardcode application annotation names and does not infer physical tables, PK/FK, JOINs, storage encoding, or lineage.

No Core evidence change and no rematerialization contract change.
