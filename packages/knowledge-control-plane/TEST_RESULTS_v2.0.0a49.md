# Test results — Analysis UI 2.0.0a49

## Необходимые проверки

- Профильные backend/API/frontend-контрактные тесты: **42 passed**.
- Python `compileall`: успешно.
- Frontend orchestration / Knowledge API boundary: успешно.
- Frontend dependency portability: успешно.
- Frontend visual contract: успешно.
- Knowledge boundary inventory: успешно.
- OpenAPI regenerated for `2.0.0a49`.
- Source manifest: regenerated and verified after final packaging cleanup.

## Покрытые изменения

- SQL-витрина с одним репозиторием планируется через `static-analysis-runner repository`.
- Workspace модели данных получает `--duckdb-memory-limit 1GB --duckdb-threads 1`.
- Логический `repository_id` отделён от runtime checkout id.
- `stderr` прогресс классифицируется как `INFO`, реальные warning/error — по содержимому.
- Последняя реальная ошибка subprocess переносится в failure карточки job.
- Финальный лог различает локальные артефакты и опубликованную revision Knowledge API.
- Checkout без credentials по-прежнему завершается быстро и не использует унаследованный VS Code `GIT_ASKPASS`.

## Не запускалось

- Production frontend build: зависимости не менялись; в контейнере отсутствует `frontend/node_modules`, сетевую переустановку не выполняли.
- Полный исторический pytest-набор: по запросу проведены только затронутые проверки.

## Известная baseline-проблема вне изменения

`tests/test_knowledge_api_publication.py` содержит три старых сценария, которые запускают `data-model-pipeline:v1` на одиночном `repository_id`; текущий контракт требует workspace. Эти три падения воспроизводятся без изменений и на исходном `2.0.0a48`, поэтому не относятся к `2.0.0a49`.
