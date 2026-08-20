# Changed files — 0.59.19

- `knowledge_layer_core/sql_producer_lineage.py`
  - reusable observed materialization producer index;
  - reusable recursive SQL producer-column traversal.
- `knowledge_layer_core/cross_artifact_data_model_builder.py`
  - delegates existing producer selection and column-origin traversal to the shared component.
- `tests/test_sql_producer_lineage.py`
  - producer priority, recursive producer traversal and terminal-source tests.
- `pyproject.toml`, `knowledge_layer_core/version.py`
  - version metadata bumped to `0.59.19`.
