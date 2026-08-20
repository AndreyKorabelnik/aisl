# Changed files — knowledge-layer-core 0.50.0

## Added

- `knowledge_layer_core/sql_analysis_schema.py`
  - SQL-only schema version, 17 typed fact tables, indexes and relation-field view.
- `knowledge_layer_core/sql_analysis_ingestion.py`
  - canonical artifact resolution, hash/fingerprint validation and streaming JSONL ingestion.
- `knowledge_layer_core/sql_analysis_builder.py`
  - atomic SQL-only knowledge-layer build and validation.
- `tests/test_sql_analysis_knowledge_layer.py`
  - synthetic contract, typed ingestion, query aggregation and tamper detection tests.
- `RELEASE_NOTES_V0.50.0.md`
- `HANDOVER_ITERATION_61.md`
- `TEST_STATUS_ITERATION_61.md`

## Updated

- `knowledge_layer_core/query.py`
  - SQL capabilities, relation/field query, SQL coverage and SQL-only overview/direct-DB support.
- `knowledge_layer_core/contracts.py`
  - explicit `sql` mode.
- `knowledge_layer_core/__init__.py`
  - public SQL schema, resolver, importer and builder exports.
- `knowledge_layer_core/version.py`
- `pyproject.toml`
  - version `0.50.0`.
- `schemas/knowledge-layer-build-request-v1.schema.json`
- `schemas/knowledge-layer-manifest-v1.schema.json`
  - `data-model | sql` mode enumeration.
- `tests/test_offline_validation.py`
  - expected package version.
- `README.md`
  - SQL analysis build and query usage.
