# aisl-reporting 0.14.0

## Назначение

Версия завершает блок переработки отчётов: обязательные ER-диаграммы модели данных, единая редакционная политика, насыщенные каталоги всех профилей и финальная модельная регрессия. Дополнительно исправлен скрытый schema-contract дефект Git Change Impact, найденный строгой проверкой локального dataset.

## Исправление Git report pipeline

`ReportRequest` в текущем runtime использует `report_request/v3`, но JSON Schema профиля `git-change-impact-report/v1` оставалась на `report_request/v2`. Из-за этого реальный `prepare_report` отклонял корректно сформированный Git dataset до LLM-rendering.

В 0.14.0:

- Git report dataset schema требует `report_request/v3`;
- добавлен полностью локальный synthetic Git artifact;
- тест выполняет настоящий `prepare_report`, включая builder, JSON Schema validation и dataset validation;
- проверяются полные changed-file и semantic-delta catalogs;
- тест больше не зависит от внешнего `GIT_CHANGE_ANALYSIS` artifact и не скрывается за skip.

Обратная совместимость с `report_request/v2` не добавлялась.

## Модельная регрессия

Текущая модель ChatGPT сформировала A/B-отчёты по одинаковым datasets для:

1. physical-only модели данных;
2. SQL Source Inventory;
3. Git Change Impact.

Результат 0.14.0:

- модель данных: 8/8 таблиц, 6/6 детальных признаков, обязательный `erDiagram`, warnings отсутствуют;
- SQL: 8/8 sources, 19/19 проверяемых fields, ограничения только в приложениях, warnings отсутствуют;
- Git: 12/12 changed paths, 6/6 проверяемых semantic details, все семь delta items, warnings отсутствуют;
- во всех новых отчётах приложения A–C присутствуют, ограничения не занимают самостоятельный основной раздел;
- observed JOIN не повышены до FK, unmapped SQL usages не назначены relation, Git runtime/downstream/test facts не придуманы.

Полный диагностический пакет поставляется отдельно как `reporting-llm-regression-0.14.0.zip`.

## Состав блока 0.13.5–0.14.0

- 0.13.5 — общая редакционная политика и приложения;
- 0.13.6 — logical/physical ER dataset и observed usage;
- 0.13.7 — мягкая ER-валидация и безопасный correction pass;
- 0.13.8 — насыщенность System Description, Workspace Interaction, FDP и NSI;
- 0.13.9 — насыщенность SQL Source Inventory и Git Change Impact;
- 0.14.0 — финальная регрессия и исправление Git request schema.

## Тесты

- compileall: passed;
- targeted Git schema/pipeline and technical richness: 7 passed, 2 skipped;
- full package suite: 87 passed, 16 skipped;
- three regression datasets: strict JSON Schema/dangling evidence validation passed;
- three generated 0.14.0 reports: advisory validation passed without warnings.
