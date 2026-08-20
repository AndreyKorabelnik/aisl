# Changed files — knowledge-layer-core 0.58.1

- `knowledge_layer_core/materialization_contracts.py`
  - removed `common-data-model` from current materializations;
  - removed `workspace-sql-mart-catalog` from planned materializations;
  - derived typed/runtime counts from registered handlers.
- `knowledge_layer_core/version.py`, `pyproject.toml`
  - version raised to 0.58.1.
- `tests/test_materialization_contracts.py`
  - replaced obsolete catalog expectations with the canonical catalog.
- `RECOVERY_CHECKPOINT_STATUS.md`
  - updated factual recovery status.
- `validation/legacy-cleanup-v0.58.1/*`
  - generated catalog and targeted validation evidence.
