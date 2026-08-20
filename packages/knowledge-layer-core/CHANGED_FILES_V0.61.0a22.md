# Changed files — Knowledge Layer Core 0.61.0a22

- `knowledge_layer_core/sql_producer_observations.py` — scope-preserving producer/config evidence and relation role metadata.
- `knowledge_layer_core/sql_producer_lineage.py` — carries relation path / FROM-JOIN provenance through traversal.
- `knowledge_layer_core/sql_workflow_target_lineage.py` — target-aware branch identity and branch-preserving terminal aggregation.
- `knowledge_layer_core/sql_target_source_mapping_builder.py` — scoped recursive placeholder resolution, branch/driver/role materialization, branch-aware value mappings and batch publication.
- `knowledge_layer_core/sql_target_source_mapping_schema.py` — `sql-target-source-mapping/v2` schema.
- `knowledge_layer_core/materialization_contracts.py` — official produced schema version updated to v2.
- `knowledge_layer_core/version.py`, `pyproject.toml` — version `0.61.0a22`.
- `tests/test_sql_producer_lineage.py` and `tests/test_sql_target_source_mapping_branch_context.py` — branch, role, placeholder/config-chain and value-mapping regressions.
