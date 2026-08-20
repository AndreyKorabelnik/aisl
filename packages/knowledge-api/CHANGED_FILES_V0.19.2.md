# Changed files — knowledge-api 0.19.2

- `knowledge_api/contract_v1/models.py` — typed response for agent-ready join semantics plus related KLC object anchors and explicit gaps.
- `knowledge_api/contract_v1/service.py` — deterministic typed-artifact selection and delegation to generic `KnowledgeQueryAdapter`; no direct DuckDB knowledge query.
- `knowledge_api/sql_query.py` — thin adapter delegates attribute-extension reads to KLC `KnowledgeLayerQuery`.
- `knowledge_api/contract_v1/contract.py` — `GET /data-model/attribute-extension-context`.
- `schemas/knowledge-v1.openapi.json` — regenerated OpenAPI contract.
- `tests/test_attribute_extension_context_api.py` — HTTP contract including polymorphic unresolved-SQL behavior, related anchors and gaps.
- `tests/test_contract_v1.py` — canonical route inventory update.
- `README.md` — new read-only endpoint and layer boundary.
- `pyproject.toml`, `knowledge_api/version.py` — version 0.19.2.

Removed: API-owned `attribute_extension_context_query.py`; KLC owns the read contract from 0.59.35.
