# Test status — aisl-reporting 0.14.0

## Code tests

- compileall: passed;
- targeted Git schema/pipeline and technical richness: 7 passed, 2 skipped;
- full package suite: 87 passed, 16 skipped.

Новый локальный Git test проходит полный `prepare_report` и подтверждает:

- `request.schema_version=report_request/v3`;
- JSON Schema validation passed;
- changed-file catalog complete;
- semantic-delta catalogs complete;
- non-empty delta types correctly published.

16 skipped относятся к прежним тестам, которым нужны внешние UCP/@900/Git artifacts. Изменённый Git request-schema path не пропущен и проверяется локально.

## Model regression

Три synthetic datasets сформированы актуальными builders и проходят strict schema/dangling-evidence validation:

- data-model physical-only: passed;
- SQL Source Inventory: passed;
- Git Change Impact: passed.

Три отчёта 0.14.0 проходят advisory report validation без warnings. Baseline 0.13.4 ожидаемо показывает missing ER/evidence warnings в соответствующих сценариях.

## Известные ограничения

- модельная A/B-проверка не является слепым benchmark;
- реальные `report_dataset.json` @900/UCP не были переданы, поэтому использованы детерминированные fixtures;
- сетевой E2E через корпоративный LLM и реальный Analysis UI выполняется после нового runtime-запуска пользователя;
- semantic Mermaid edge-level validation остаётся отдельной возможной доработкой; текущий validator проверяет обязательные непустые ER-блоки и ограниченный diagram dataset.

Wheel: `aisl_reporting-0.14.0-py3-none-any.whl`; SHA-256 `c5c3bd0d8c43d95d39d2571eb05766d96675121b9784d6f5ffc29bb6beeedaa0`.
