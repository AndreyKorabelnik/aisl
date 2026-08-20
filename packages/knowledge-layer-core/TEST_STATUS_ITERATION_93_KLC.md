# Статус тестирования — итерация 93 KLC

## Сфокусированные тесты

Проверены:

- разрешение known placeholder после неизвестного корневого placeholder;
- повторный repository-local поиск при пустом static candidate set;
- отсутствие разрешения по нерелевантному binding;
- сохранение неоднозначности без нужного значения;
- workflow-context materialization;
- запрос workflow bindings;
- ранжирование SQL target candidates.

Результат: **12 passed, 0 failed**.

## Реальный smoke

Источник: неизменённый canonical SQL artifact `datamart_profile_fl`.

Результат KLC build:

- status: `complete`;
- `sql_workflow_context_file`: 934 rows;
- `sql_placeholder_binding_resolution`: 254 rows;
- workflow `b2c_profile_fl_epk_client.yaml` достигает ровно одного `epk_client/prep_src.sql`;
- тот же workflow достигает ровно одного `epk_client/epk_client.sql`;
- оба пути имеют status `resolved`;
- финальный SQL достигается на hop 4.

## Не выполнялось

Полный KLC suite не запускался. Не менялись schema, ingestion, core evidence, data-model, topology, API и non-SQL materialization. Изменение покрыто сфокусированными тестами и реальным KLC build.
