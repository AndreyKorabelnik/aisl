# Changed files — knowledge-layer-core 0.53.3

- `knowledge_layer_core/foreign_data_queries.py`
  - normalizes canonical scalar `source_field/storage_field` FDP rows into the common field-mapping view used by mechanical cases;
  - preserves raw facts unchanged;
  - avoids duplicate mappings when an aggregated `field_mappings` array already exists.
- `tests/test_suite_scope.py`
  - adds a regression proving scalar Core source-to-storage rows bridge to storage-to-access mappings by exact physical field identity.
- `pyproject.toml`, `knowledge_layer_core/version.py`
  - version `0.53.3`.
- release/test/AT900 validation notes.
