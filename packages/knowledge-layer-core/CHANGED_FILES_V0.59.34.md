# KLC 0.59.34 changed files

- `knowledge_layer_core/cross_artifact_data_model_builder.py` — align the published manifest with the existing cross-artifact target/source mart already materialized by the builder: publish `cross-artifact-target-source-mapping` and capability `common.sql-target-source-mapping`.
- `tests/test_cross_artifact_data_model_mapping.py` — regression that the runtime result/manifest publish the declared target/source capability and mart.
- `pyproject.toml`, `knowledge_layer_core/version.py` — version 0.59.34.
- release/test metadata for this checkpoint.
