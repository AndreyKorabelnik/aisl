# Changed files — static-analysis-runner 0.9.54

- `static_analysis_runner/knowledge_planning.py`
  - derives `current_typed` availability from registered KLC runtime metadata;
  - removes `common-data-model` from internal materializations;
  - removes obsolete legacy bridge descriptions for migrated materializations.
- `static_analysis_runner/version.py`, `pyproject.toml`
  - version raised to 0.9.54.
- `tests/test_knowledge_planning.py`
  - catalog fixtures and assertions migrated to current runtime truth.
- `tests/test_knowledge_execution_planning.py`
  - removed obsolete planned/current fixture mutation.
- `RECOVERY_CHECKPOINT_STATUS.md`
  - updated factual recovery status.
- `validation/legacy-cleanup-v0.9.54/*`
  - generated catalog and execution smoke evidence.
