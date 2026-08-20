# knowledge-layer-core 0.59.35 — attribute-extension read contract

Adds a KLC-owned read-only query for `data-model-attribute-extension-context/v1`.

The query exposes already materialized join semantics, storage/reference expressions, SQL anchors, physical candidates, provenance, diagnostics, related object anchors and explicit gaps. It performs no relationship classification, identity matching, physical-table resolution or SQL generation.

This keeps Knowledge API thin: API consumers can delegate to `KnowledgeLayerQuery` instead of reimplementing DuckDB knowledge queries.
