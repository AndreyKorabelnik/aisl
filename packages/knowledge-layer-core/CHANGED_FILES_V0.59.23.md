# Changed files — 0.59.23

- `knowledge_layer_core/sql_producer_lineage.py`
  - carries terminal workflow context to ultimate origins.
- `knowledge_layer_core/sql_target_source_mapping_builder.py`
  - exact evidence-only placeholder resolution for product source relations; preserves unresolved placeholders and publishes explicit gaps/status.
- `tests/test_sql_producer_lineage.py`
  - updates terminal-origin contract for workflow context.
- `tests/test_sql_target_source_mapping_semantics.py`
  - proves partial bindings are never guessed and complete exact bindings are substituted only in matching context.
- `pyproject.toml`, `knowledge_layer_core/version.py`
  - version metadata bumped to `0.59.23`.
