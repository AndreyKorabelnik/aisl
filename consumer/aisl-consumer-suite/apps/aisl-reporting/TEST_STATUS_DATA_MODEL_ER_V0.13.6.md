# Test status — aisl-reporting 0.13.6

## Выполнено

- Python compileall: passed.
- Targeted ER/report contract tests: 20 passed.
- Full package tests: 72 passed, 16 skipped.

## Что проверено

- полная logical ER при количестве связей до 30;
- deterministic overview logical/physical ER для крупных наборов;
- physical ER содержит только declared schema relationships;
- observed SQL/JOOQ/data-movement relationships публикуются отдельно;
- physical-only dataset содержит ER даже без логической модели;
- PK и колонки добавляются в физические table nodes;
- новый prompt использует только канонические diagram sections;
- dataset schema требует три независимых diagram sections;
- Mermaid normalization и общая редакционная политика не регрессировали.

## Skipped

16 существующих тестов требуют внешних реальных UCP, @900 или Git analysis artifacts, которых нет в локальной поставке. Изменённые unit/contract paths не пропущены.

## Известные ограничения

- ER dataset не генерирует готовый Mermaid: это задача LLM renderer следующей итерации и runtime validation.
- При более чем 30 отношениях diagram dataset является детерминированным обзором, а не полной единой диаграммой.
- В entity-only physical ER используется bounded representative catalog текущего detail level; полный физический каталог остаётся доступен через Knowledge Layer/API.

## Wheel

- `aisl_reporting-0.13.6-py3-none-any.whl`
- SHA-256: `1fa4ea7a90ac4071603f71ab62526f82205edbe321780800e1c65a6b9c1f739b`
- Проверено наличие нового `er_dataset.py`, renderer prompt, dataset schema и общей editorial policy внутри wheel.
