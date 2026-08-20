# Changed files — 0.59.25

- `knowledge_layer_core/sql_target_source_mapping_builder.py` — terminal value-source field identity now requires both observed relation and column; unresolved expression/template terminals stay raw/explain facts and become explicit product gaps instead of bogus resolved value sources.
- `tests/test_sql_target_source_mapping_semantics.py` — regression for the terminal field-identity invariant.
- `pyproject.toml`, `knowledge_layer_core/version.py` — version 0.59.25.
