# Changed files — analysis-ui 2.0.0a25

- `src/analysis_ui/api/generic_v1/models.py` — prepared assistant-context contracts and context-scoped conversation responses.
- `src/analysis_ui/api/generic_v1/contract.py` — assistant-context CRUD and conversation API.
- `src/analysis_ui/runtime/assistant_contexts.py` — validation and lifecycle of pinned source/datamart/PDM revisions.
- `src/analysis_ui/runtime/store.py` — durable context and conversation metadata; no semantic facts are copied from DuckDB.
- `src/analysis_ui/runtime/knowledge_publication.py` — read-only Knowledge API revision lookup.
- `src/analysis_ui/runtime/context.py`, `routes.py`, `app.py` — runtime wiring and endpoints.
- `tests/test_assistant_contexts.py`, contract/lifecycle/OpenAPI tests — focused regression coverage.
- `docs/api/generic-v1.openapi.json`, version and release metadata — synchronized public contract.
