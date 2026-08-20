# Changed files — Analysis UI 2.0.0a52

## Backend and API

- `src/analysis_ui/api/generic_v1/models.py` — удалены `RemoteRepositoryAuth` и поле `auth` из remote repository candidate.
- `src/analysis_ui/runtime/repositories.py` — checkout использует только server environment; удалено временное request-level хранение credentials.
- `src/analysis_ui/runtime/jobs.py` — сообщение checkout-ошибки указывает на серверную настройку Bitbucket.
- `docs/api/generic-v1.openapi.json` — удалена схема request-level auth.

## Frontend

- `frontend/src/components/AssistantContextRepositoryPreparation.vue` — удалены поля имени пользователя и token/пароля; добавлена информационная подсказка о server environment.
- `frontend/src/services/api.ts` — repository discovery больше не формирует `auth` payload.
- `frontend/src/services/types.ts` — удалены frontend-типы Bitbucket credentials.
- `frontend/package.json`, `frontend/package-lock.json` — версия frontend `2.0.0-alpha.23`.

## Documentation and tests

- `README.md`, `docs/runtime/OPERATIONS.md`, `docs/runtime/ARCHITECTURE.md` — server-only authentication contract.
- `tests/test_checkout_credentials.py` — environment-only checkout and noninteractive failure.
- `tests/test_generic_api_contract.py`, `tests/test_runtime_backend.py` — API rejects request credentials and does not persist secrets.
- `tests/test_assistant_context_frontend.py` — no credential controls in frontend.
- `VERSION`, `pyproject.toml`, `src/analysis_ui/__init__.py`, `tests/test_module_baseline.py` — version `2.0.0a52`.
