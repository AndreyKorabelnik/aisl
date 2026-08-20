# Changed files — analysis-ui 2.0.0a29

- `src/analysis_ui/api/generic_v1/models.py` — typed successful-job candidate and import requests.
- `src/analysis_ui/runtime/analysis_artifacts.py` — deterministic candidate discovery and import of an existing job publication without re-publication.
- `src/analysis_ui/runtime/routes.py`, `api/generic_v1/contract.py` — candidate-list and from-job endpoints.
- `src/analysis_ui/runtime/context.py` — passes the existing job artifact registry to the analysis-artifact service.
- `frontend/src/services/types.ts`, `api.ts` — typed candidate/import client.
- `frontend/src/views/AssistantContexts.vue` — two registration modes: successful job or server DuckDB path.
- `tests/test_analysis_artifacts.py` — immutable-revision reuse, no-republication, duplicate and invalid-job regression.
- `tests/test_assistant_context_frontend.py`, `test_generic_api_contract.py` — wizard and canonical API contract updates.
- OpenAPI, README, validation evidence, version and release manifests synchronized.
