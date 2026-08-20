# Knowledge-layer query contract v1

`KnowledgeLayerQuery` accepts an artifact directory, a manifest directory, or a direct DuckDB path.
It discovers `knowledge-layer.duckdb` first and accepts `workspace.duckdb` as a transition-compatible input.

## Common API

- `get_overview()`
- `list_entities()` / `get_entity()`
- `list_effective_fields()` / `list_effective_associations()`
- `list_tables()` / `get_table()`
- `list_keys()`
- `list_relationships()`
- `get_type_neighborhood()`
- `search_source_observations()`
- `list_gaps()`

The established WKL method names remain available for existing consumers.

## Capabilities

Capabilities are derived from actually materialized relations rather than assumed from scope size:

- `common.data-model`
- `common.effective-model`
- `common.physical-model`
- `common.source-observations`
- `common.keys`
- `common.relationships`
- `workspace.cross-repository`
- `framework.tsa`

The core never fabricates missing extension data. Optional cross-repository sections are empty when the corresponding relations are absent.
