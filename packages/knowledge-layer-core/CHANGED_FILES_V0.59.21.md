# Changed files — 0.59.21

- `knowledge_layer_core/sql_producer_observations.py`
  - derives reusable observed relation materialisations and workflow dependencies from `knowledge_layer_sql/v2`.
- `knowledge_layer_core/sql_target_source_mapping_schema.py`
  - adds `sql-target-source-mapping/v1`, raw recursive source mappings, value-source mappings and explicit gaps.
- `knowledge_layer_core/sql_target_source_mapping_builder.py`
  - composes target lineage through observed physical producers and materialises separate raw/value surfaces.
- `knowledge_layer_core/sql_value_source_semantics.py`
  - exact storage identity and evidence-backed parent-key value-origin normalisation.
- `knowledge_layer_core/materialization_contracts.py`
  - registers the typed `sql-target-source-mapping` composition contract.
- `knowledge_layer_core/materialization_runtime.py`
  - registers generic runtime handler with required SQL knowledge and optional model-storage semantics.
- `tests/test_sql_target_source_mapping_semantics.py`
  - generic structured-expression + observed-parent-key semantic test.
- `tests/test_materialization_contracts.py`, `tests/test_materialization_runtime.py`
  - updated registry/catalog contract expectations.
- `pyproject.toml`, `knowledge_layer_core/version.py`
  - version metadata bumped to `0.59.21`.
