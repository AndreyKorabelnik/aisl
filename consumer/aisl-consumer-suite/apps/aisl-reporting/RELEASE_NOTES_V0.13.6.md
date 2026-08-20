# aisl-reporting 0.13.6

## Назначение

Версия вводит отдельный доказательный ER dataset для отчёта модели данных. Логические отношения, объявленные физические связи схемы и наблюдаемые SQL/JOOQ/data-movement связи больше не смешиваются.

## Новый ER-контракт

`data-model-report/v1` публикует три независимых раздела:

- `sections.diagrams.logical_er` — логические сущности и наблюдаемые отношения объектной модели;
- `sections.diagrams.physical_er` — физические таблицы и только объявленные schema relationships;
- `sections.diagrams.observed_usage` — наблюдаемые SQL/JOOQ/data-movement связи использования.

Физический ER больше не строится по bounded списку наблюдаемых JOIN.

## Полные и крупные модели

- если объявленных отношений не более 30, в ER dataset включаются все;
- при большем количестве формируется детерминированный обзор до 30 отношений с round-robin выборкой по схемам;
- для логической модели используется аналогичная выборка по пакетам;
- dataset публикует total/selected counts, `relationships_truncated`, `selection_policy` и `domain_groups`;
- если рёбер нет, формируется `entity_only` ER с доступными сущностями или представительными таблицами.

## Узлы ER

Для выбранных логических сущностей передаются наблюдаемые атрибуты и ключи. Для физических таблиц запрашиваются колонки, PK и другие declared keys. Необязательная ошибка получения table detail не скрывается: таблица остаётся в диаграмме, а dataset получает явный diagnostic `physical_er_table_detail_failed`.

## Prompt и schema

Renderer prompt переведён на новый канонический ER-контракт и прямо запрещает рисовать observed usage как declared FK. Dataset schema требует наличие `logical_er`, `physical_er` и `observed_usage`.

## Совместимость

Старый `sections.diagrams.logical_relationships` удалён. Обратная совместимость с прежним diagram dataset не поддерживается.

## Тесты

- `compileall`: пройден;
- новые ER tests: logical complete, physical overview, entity/physical-only и separation observed usage;
- затронутые тесты: `20 passed`;
- полный набор AISL Reporting: `72 passed, 16 skipped`;
- skipped относятся к отсутствующим внешним реальным UCP/@900/Git artifacts.
