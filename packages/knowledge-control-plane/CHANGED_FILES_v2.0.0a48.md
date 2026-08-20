# Changed files — Analysis UI 2.0.0a48

- `src/analysis_ui/runtime/observability.py` — request ID, безопасное журналирование, ротация файла.
- `src/analysis_ui/runtime/app.py` — HTTP middleware и журналирование обработанных ошибок.
- `src/analysis_ui/runtime/assistant.py` — трасса выполнения Knowledge Assistant.
- `src/analysis_ui/runtime/store.py` — сохраняемые журналы контекстов чата.
- `src/analysis_ui/runtime/routes.py` — API журналов чата и общего runtime-лога.
- `src/analysis_ui/runtime/settings.py` — настройки файла и ротации.
- `src/analysis_ui/runtime/diagnostics.py` — диагностика расположения runtime-лога.
- `src/analysis_ui/api/generic_v1/models.py` — контракты технического журнала.
- `src/analysis_ui/api/generic_v1/contract.py` — публичные операции журнала.
- `frontend/src/components/AssistantTechnicalLog.vue` — панель технического журнала.
- `frontend/src/components/AssistantChat.vue` — постоянная карточка ошибки и live polling журнала.
- `frontend/src/services/api.ts`, `frontend/src/services/types.ts` — API и типы журнала, сохранение деталей ошибки.
- `tests/test_assistant_observability.py` — success/failure/request-ID проверки.
- `tests/test_assistant_context_frontend.py`, `tests/test_generic_api_contract.py` — контрактные проверки.
- `README.md`, OpenAPI, версия и release metadata.
