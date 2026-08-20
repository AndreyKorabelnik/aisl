# Changed files — knowledge-api 0.19.0

- `knowledge_api/data_model_lineage_query.py` — canonical v6 reader plus compact target-source projection.
- `knowledge_api/contract_v1/models.py` — compact S2T response and v2 detailed lineage models.
- `knowledge_api/contract_v1/service.py` — target-source routing to cross-artifact capability and v6 detail routing.
- `knowledge_api/contract_v1/contract.py` — compact endpoint parameters/default one-call limit.
- `knowledge_api/version.py` — 0.19.0.
- `schemas/knowledge-v1.openapi.json` — regenerated public contract.
- `tests/test_data_model_lineage_api.py` — v6 detail + compact S2T semantics.
- `tests/test_sql_relations_api.py` — SQL-only artifact no longer accepted as product S2T source.
