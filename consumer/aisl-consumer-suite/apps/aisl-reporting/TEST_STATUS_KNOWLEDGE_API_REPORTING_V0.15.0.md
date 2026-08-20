# Test status — aisl-reporting 0.15.0

## Исходное дерево

- Полная регрессия модуля: `88 passed, 2 skipped`.
- Пропуски: только два optional-теста внешнего `GIT_CHANGE_ANALYSIS` fixture.
- `compileall aisl_reporting tests`: passed.
- CLI surface: только `prepare`, `build`, `compare`.

Полная регрессия Reporting была выполнена, потому что изменились публичный request contract, CLI, source routing и профиль data model. Остальные модули не тестировались повторно.

## Реальный smoke

Использованы:

- Knowledge API 0.16.0;
- опубликованный реальный `knowledge_execution_result/v1`;
- 5 knowledge artifacts;
- 17 capabilities;
- effective-data-model и physical-data-model;
- aisl-reporting 0.15.0.

Результат:

- `prepare`: passed;
- `build` с FileRenderer: passed;
- status: `completed`;
- warnings: 0;
- revision provenance: preserved;
- direct input artifact: null;
- selected model kind: `effective-data-model`;
- logical objects: 2;
- physical objects: 2;
- deterministic ER: applied;
- dataset schema validation: passed.
