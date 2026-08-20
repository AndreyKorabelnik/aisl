# Changed files — 0.59.20

- `knowledge_layer_core/cross_artifact_data_model_schema.py`
  - schema v6;
  - new `cross_artifact_target_source_mapping` mart and indexes.
- `knowledge_layer_core/cross_artifact_data_model_builder.py`
  - materializes terminal SQL source relation/column independently of logical-model binding;
  - retains projection, transformation, materialization and workflow-dependency provenance.
- `knowledge_layer_core/materialization_contracts.py`
  - publishes `cross-artifact-data-model-mapping/v6` and `common.sql-target-source-mapping`.
- `tests/test_cross_artifact_data_model_mapping.py`
  - integration regression for `target -> physical staging -> producer -> ultimate physical source` without Java/logical source binding.
- `pyproject.toml`, `knowledge_layer_core/version.py`
  - version metadata bumped to `0.59.20`.
