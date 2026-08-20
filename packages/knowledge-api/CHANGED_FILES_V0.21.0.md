# Changed files — knowledge-api 0.21.0

- `knowledge_api/contract_v1/service.py` — replace legacy target-source-mapping lookup with the canonical SQL query service and preserve recursive lineage/gaps.
- `knowledge_api/contract_v1/models.py` — replace the legacy compact S2T response classes with the canonical recursive-lineage response envelope.
- `knowledge_api/contract_v1/contract.py` — expose `repo_id` and `lineage_status` filters already supported by KLC and Knowledge Assistant.
- `tests/test_sql_relations_api.py` — prove canonical `sql-observed-data-usage` alone serves target-column lineage and filters reach KLC.
- `tests/test_data_model_lineage_api.py` — clarify the negative contract: revisions without canonical SQL-lineage knowledge are rejected explicitly.
- `schemas/knowledge-v1.openapi.json` — regenerated public OpenAPI.
- `README.md` — document recursive-lineage semantics and filters.
- `knowledge_api/version.py`, `pyproject.toml` — version 0.21.0.
