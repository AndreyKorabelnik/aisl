# Архитектура AISL Reporting 0.15.0

## Канонический источник

Reporting работает с неизменяемой ревизией Knowledge API. Ревизия содержит результат исполнения знаний, перечень типизированных knowledge artifacts и опубликованные capabilities.

Профиль отчёта объявляет `KnowledgeRequirement`:

- обязательный `model_kind`, когда профиль привязан к конкретной модели;
- обязательные capabilities;
- необязательные модели/capabilities для обогащения;
- признак API projection.

## Разрешение входа

1. При отсутствии `revision_id` Reporting получает активную ревизию системы.
2. Из ревизии выбирается ровно один артефакт, удовлетворяющий требованию профиля.
3. Отсутствие артефакта является явной ошибкой.
4. Несколько различных подходящих артефактов являются неоднозначностью и также блокируют запуск.
5. Для API-projection профилей локальный доступ к DuckDB не требуется.
6. Для ещё не переведённых профилей разрешён только опубликованный `file://` артефакт выбранной ревизии; прямой пользовательский путь не принимается.

## Data model report

`data-model-report/v1` является первым полностью API-проекционным профилем:

- primary knowledge: `effective-data-model` + `common.effective-data-model`;
- optional knowledge: physical model + logical/physical mapping;
- логические таблицы/поля/связи читаются через `/data-model/*`;
- физическая модель читается через `/physical-model/*`;
- coverage читается через `/coverage`;
- ER dataset и Mermaid строятся детерминированно.

## Удалённый legacy

Удалены:

- `input_kind=knowledge_layer`;
- прямой вход общей `knowledge-layer.duckdb`;
- artifact/package pipelines Reporting;
- публичные `artifact-*` и `package-*` CLI-команды;
- fixture-тесты общей базы.

Концептуальные и составные модели должны быть знаниями KLC, а не отдельным обходным синтезом Reporting.

## Provenance

В `report_dataset` и `report_run_manifest` сохраняются:

- system ID;
- точный revision ID;
- execution metadata;
- выбранный artifact ID;
- `model_kind` и schema version;
- materialization source;
- content fingerprint;
- capabilities, coverage и diagnostics.

Финальный manifest использует уже разрешённый request, а не исходный запрос без revision ID.
