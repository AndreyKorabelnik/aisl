# Changed files — Analysis UI 2.0.0a47

## Backend

- `src/analysis_ui/api/generic_v1/models.py` — deferred checkout request flag.
- `src/analysis_ui/runtime/repositories.py` — ephemeral checkout credentials, disabled external credential helpers, fail-fast checkout.
- `src/analysis_ui/runtime/jobs.py` — checkout credential lifecycle and visible failure messages.
- `src/analysis_ui/runtime/pipeline.py` — built-in physical-model planning without a separate analysis profile.

## Frontend

- `frontend/src/views/Home.vue` — priority master allowlist.
- `frontend/src/components/AssistantContextRepositoryPreparation.vue` — canonical profiles, PDM behavior, Bitbucket credentials.
- `frontend/src/services/api.ts` — deferred repository discovery and auth input.
- `frontend/src/services/types.ts` — discovery/auth contracts.
- `frontend/.env.example`, `frontend/README.md`, `config/README.md` — priority master configuration.

## Contracts and tests

- `docs/api/generic-v1.openapi.json` — regenerated API contract.
- `tests/test_checkout_credentials.py` — credential lifecycle and prompt blocking.
- `tests/test_runtime_backend.py` — inherited VS Code askpass regression and PDM flow.
- `tests/test_assistant_context_frontend.py`, `tests/test_revision_first_ui.py`, `tests/test_module_baseline.py` — UI and release expectations.
- `scripts/verify_frontend_visual_baseline.py` — intentional UI change registration.
