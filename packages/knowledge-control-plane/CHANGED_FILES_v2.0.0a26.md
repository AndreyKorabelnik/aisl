# Changed files — analysis-ui 2.0.0a26

- `src/analysis_ui/runtime/assistant.py` — in-process Knowledge Assistant execution over pinned prepared-context revisions.
- `src/analysis_ui/runtime/context.py`, `routes.py` — runtime wiring and context-scoped question endpoint.
- `src/analysis_ui/api/generic_v1/contract.py` — public `POST /assistant-contexts/{context_id}/questions` contract.
- `pyproject.toml` — `knowledge-assistant>=0.13.1,<0.14.0` runtime dependency.
- `tests/test_assistant_contexts.py` — HTTP chat execution and conversation persistence regression.
- OpenAPI, version and release metadata synchronized.
