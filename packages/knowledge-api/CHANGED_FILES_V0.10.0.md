# Changed files — knowledge-api 0.10.0

- `knowledge_api/sql_query.py`: forwards SQL relation view and classification coverage.
- `knowledge_api/contract_v1/contract.py`: adds `view=business_sources|technical|all`.
- `knowledge_api/contract_v1/service.py`: maps relation semantic roles.
- `knowledge_api/contract_v1/models.py`: adds semantic role and classification DTOs.
- `tests/test_sql_relations_api.py`: default-hidden and diagnostic-view contracts.
- `schemas/knowledge-v1.openapi.json`: regenerated.
- version and KLC dependency updated.
