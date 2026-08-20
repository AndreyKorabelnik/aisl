# Test results — Analysis UI 2.0.0a48

## Выполнено

- `python -m compileall -q src` — успешно.
- Профильный набор observability/assistant/API/store/frontend contracts — **47 passed, 61 deselected**.
- `scripts/check_frontend_contract.py` — успешно.
- `scripts/verify_frontend_dependency_portability.py` — успешно, 310 package-lock записей используют публичные HTTPS URL.
- `scripts/verify_frontend_visual_baseline.py` — успешно, 12 сохранённых и 12 workspace-секций подтверждены.
- `scripts/verify_knowledge_boundary_inventory.py` — успешно.
- Отдельный observability regression: success, 502 failure, request ID, persistent trace, clear logs, secret redaction — **3 passed**.

## Не выполнялось

- Полный исторический pytest-набор не запускался: изменение локализовано в наблюдаемости runtime/assistant и публичном контракте журналов.
- `npm ci && npm run build` не завершён в среде сборки: внутреннее npm-зеркало вернуло `404` для `vue-tsc-2.2.12.tgz`. `package.json` и зависимости не изменялись; source-level frontend contracts и dependency portability прошли.

## Фактический результат

- Ошибка Knowledge Assistant сохраняется в контекстном журнале с `request_id`, `exchange_id`, стадией, длительностью, типом исключения и безопасной причиной.
- UI показывает постоянную карточку ошибки и автоматически раскрывает технический журнал.
- Общий backend-журнал ротируется в `${ANALYSIS_UI_RUNTIME_ROOT}/logs/analysis-ui.log`.
- Текст вопроса и секретные значения в журнал не записываются.
