# knowledge-api 0.13.0

- Adds a deterministic target-centric SQL lineage endpoint over the existing `sql_recursive_column_lineage` and `sql_scoped_lineage_gap` facts.
- Preserves every terminal source branch, transformation path, resolution status and repository-relative evidence without selecting or inventing a preferred source.
- Supports exact target relation, optional target column, repository and lineage-status filters, API offset/limit pagination, and optional scoped gaps.
- Requires `knowledge-layer-core>=0.52.3,<1.0.0`.
- Regenerates the canonical OpenAPI document for version 0.13.0.
