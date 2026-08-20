# Changed files — 0.54.0

- `knowledge_layer_core/code_declared_model_schema.py` — typed DuckDB schema for `code-declared-data-model/v1`.
- `knowledge_layer_core/code_declared_model_ingestion.py` — strict import of Runner-registered `java-type-structure-evidence/v1` by `artifact_kind + schema_version`.
- `knowledge_layer_core/code_declared_model_builder.py` — repository/workspace materialization, inherited fields, declared type-reference relationships, coverage, gaps and provenance.
- `knowledge_layer_core/materialization_contracts.py` — promotes `code-declared-data-model` to current typed materialization and removes the active `data-model` Task semantic route for this knowledge.
- `knowledge_layer_core/__init__.py`, `knowledge_layer_core/version.py`, `pyproject.toml` — public API and version 0.54.0.
- `tests/test_code_declared_model_builder.py` — typed import, materialization, workspace isolation, no-legacy fallback and fingerprint validation.
- `tests/test_materialization_contracts.py`, `tests/test_offline_validation.py` — updated catalog and version expectations.
- `validation/knowledge-materialization-contracts-v2-0.54.0.*` — deterministic contract exports.
- `validation/code-declared-data-model-smoke-v0.54.0.json` — real Runner 0.9.46 → KLC smoke.
