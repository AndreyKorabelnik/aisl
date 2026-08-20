# Changed files — analysis-ui 2.0.0a28

- `frontend/src/views/AssistantContexts.vue` — ready-DuckDB registration, source/datamart/PDM selection and prepared-context creation.
- `frontend/src/views/AssistantContext.vue` — pinned-revision context header and standard chat host.
- `frontend/src/components/AssistantChat.vue` — Markdown/SQL conversation using the existing `Renderer` and context-scoped backend API.
- `frontend/src/services/api.ts`, `types.ts` — typed analysis-artifact and assistant-context clients; extended timeout for LLM-backed questions.
- `frontend/src/router/index.ts`, `App.vue` — routes and top-level navigation inside the existing UI.
- `src/analysis_ui/runtime/app.py` — production frontend fallback routes for direct context URLs.
- `tests/test_assistant_context_frontend.py`, `tests/test_runtime_backend.py` — wizard/chat contracts and production-route regression.
- Frontend visual baselines, README, OpenAPI metadata, version and release manifests synchronized.
