# Changed files — 0.59.22

- `knowledge_layer_core/sql_workflow_target_lineage.py`
  - fixes recursive CTE alias/rename traversal and excludes non-value SQL usage roles from target value lineage.
- `knowledge_layer_core/sql_producer_lineage.py`
  - enforces the same value-role rule recursively across observed producers; carries terminal semantic-role classification for strict frontier handling.
- `knowledge_layer_core/sql_producer_observations.py`
  - attaches existing SQL relation semantic-role facts to traversal relations; roles classify unresolved frontiers only and never select producers.
- `knowledge_layer_core/sql_target_source_mapping_builder.py`
  - preserves unresolved intermediate raw frontiers, excludes them from product value sources, and emits `intermediate_producer_unresolved` diagnostics.
- `tests/test_sql_producer_lineage.py`
  - adds generic regression for excluding window partition/order controls from producer value origins.
- `pyproject.toml`, `knowledge_layer_core/version.py`
  - version metadata bumped to `0.59.22`.
