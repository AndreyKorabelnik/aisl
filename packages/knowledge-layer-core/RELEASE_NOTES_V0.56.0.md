# Release Notes — knowledge-layer-core 0.56.0

Adds the first KLC-to-KLC composite knowledge materialization.

## Added

- `effective-data-model/v1` deterministic DuckDB schema and builder.
- `model-domain-cluster-view/v1` technical package and relationship grouping view.
- KLC-owned `effective-data-model` handler in `knowledge_materialization_runtime/v1`.
- Logical-first composition of code-declared, physical and logical/physical-mapping knowledge artifacts.
- Separate inventory of unmapped physical tables and columns.
- Cross-layer coverage and provenance for entities, fields, keys and relationships.
- Explicit inherited-field gap when persistence-inheritance evidence is absent.

## Semantic policy

Logical objects are never replaced by physical objects. Physical identifiers are attached only through explicit matched mapping records. Name similarity, JPA default naming, hidden fallback and legacy conceptual-model ingestion are unsupported. Package domains and relationship clusters are technical deterministic groupings, not business-domain interpretation.
