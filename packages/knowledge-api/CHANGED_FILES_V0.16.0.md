# Changed files — knowledge-api 0.16.0

- `knowledge_api/publication.py` — execution-result publication and artifact discovery.
- `knowledge_api/effective_data_model_query.py` — deterministic effective model projection.
- `knowledge_api/contract_v1/models.py` — new revision/publication/artifact contracts.
- `knowledge_api/contract_v1/store.py` — new immutable revision storage schema.
- `knowledge_api/contract_v1/service.py` — typed artifact routing and validation.
- `knowledge_api/contract_v1/contract.py` — artifact/capability endpoints.
- `knowledge_api/contract_v1/runtime.py` — guarded artifact paths.
- `knowledge_api/cli.py` — `--execution-result` publication.
- `knowledge_api/query_source.py`, `knowledge_api/sql_query.py` — typed artifact query source.
- `knowledge_api/data_model_query.py` — removed.
- `schemas/knowledge-v1.openapi.json` — regenerated.
- tests — rewritten for knowledge execution publication; old combined-model tests removed.
