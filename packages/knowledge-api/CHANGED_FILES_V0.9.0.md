# Changed files — knowledge-api 0.9.0

- `knowledge_api/sql_query.py` — cached generic KLC adapter, SQL capability checks and offset pagination over KLC continuation tokens.
- `knowledge_api/contract_v1/models.py` — SQL relation, field, coverage and evidence response DTOs.
- `knowledge_api/contract_v1/service.py` — SQL-only publication validation, SQL relation query service and data-model capability guard.
- `knowledge_api/contract_v1/contract.py` — canonical SQL relation endpoint.
- `knowledge_api/version.py`, `pyproject.toml` — version 0.9.0 and KLC 0.50.0+ dependency.
- `tests/test_sql_relations_api.py` — real DuckDB publication and query tests.
- `tests/test_contract_v1.py` — canonical path set updated.
- `schemas/knowledge-v1.openapi.json` — regenerated public contract.
- `README.md`, `RELEASE_NOTES.md`, `TEST_RESULTS.md`, `ITERATION_31_HANDOVER.md` — operational documentation.
