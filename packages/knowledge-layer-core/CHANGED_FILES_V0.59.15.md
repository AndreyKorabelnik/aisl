# Changed files — 0.59.15

- `knowledge_layer_core/cross_artifact_data_model_schema.py` — schema v4; replaces field-only physical lineage with canonical `cross_artifact_value_origin_physical_lineage`.
- `knowledge_layer_core/cross_artifact_data_model_builder.py` — materializes logical-field, storage-identity, reference-key and object-presence origins from the existing proof graph and storage metadata.
- `knowledge_layer_core/materialization_contracts.py` — publishes schema v4 and `common.value-origin-physical-lineage` capability.
- `tests/test_cross_artifact_data_model_mapping.py` — current logical-storage fixture and canonical-v4/no-legacy-table contract assertion.
- `knowledge_layer_core/version.py`, `pyproject.toml` — version 0.59.15.
