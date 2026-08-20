# Changed files — knowledge-layer-core 0.53.0

- `knowledge_layer_core/physical_model_schema.py` — typed DuckDB schema for deterministic `physical-model/v1` facts.
- `knowledge_layer_core/physical_model_ingestion.py` — manifest/hash validation and JSONL ingestion.
- `knowledge_layer_core/physical_model_builder.py` — standalone physical-model knowledge-layer builder and integrity checks.
- `knowledge_layer_core/__init__.py` — public physical-model API exports.
- `knowledge_layer_core/version.py`, `pyproject.toml` — version 0.53.0.
- `tests/test_physical_model_knowledge_layer.py` — focused materialization, partial coverage, integrity and replacement tests.
