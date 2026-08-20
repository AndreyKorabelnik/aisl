# Changed files 0.13.0

- `knowledge_api/sql_query.py` — adapter for the existing recursive target-column lineage query.
- `knowledge_api/contract_v1/models.py` — public lineage path, gap, summary and response contracts.
- `knowledge_api/contract_v1/service.py` — revision-aware mapping from KLC facts to API models.
- `knowledge_api/contract_v1/contract.py` — `GET .../sql/target-column-lineage`.
- `knowledge_api/version.py` — package version 0.13.0.
- `tests/test_sql_relations_api.py` — HTTP regression for branches, gaps, filters and pagination.
- `tests/test_contract_v1.py` — public path contract.
- `schemas/knowledge-v1.openapi.json` — regenerated canonical OpenAPI.
- `pyproject.toml` — version and KLC dependency floor.
- `README.md` — endpoint usage and semantic limits.
- `RELEASE_NOTES_V0.13.0.md`
- `TEST_STATUS_ITERATION_88_API.md`
- `HANDOVER_ITERATION_88_API.md`
