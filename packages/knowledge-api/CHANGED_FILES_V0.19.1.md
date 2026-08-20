# Changed files — knowledge-api 0.19.1

- `knowledge_api/sql_query.py` — thin grouped read projection over KLC `sql-target-value-source-mapping`.
- `knowledge_api/contract_v1/service.py` — route target-column lineage to product S2T artifact; optional PDM-backed target display spelling.
- `tests/test_data_model_lineage_api.py` — cross-artifact-only revision no longer satisfies product S2T endpoint.
- `tests/test_sql_relations_api.py` — grouped value-source + gap-only adapter regression.
- `pyproject.toml`, `knowledge_api/version.py` — version 0.19.1.
