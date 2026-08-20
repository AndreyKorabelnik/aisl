# aisl-reporting 0.13.9

## Назначение

Версия завершает переработку технических отчётных профилей: SQL Source Inventory и Git Change Impact. Отчёты показывают полный извлечённый каталог и конкретные semantic deltas до ограничений, не возвращая старые LLM-analysis контракты и не добавляя новые эвристики.

## SQL Source Inventory

- top-source budgets увеличены до 15 / 40 / 80 для executive / standard / detailed;
- usage-profile budgets увеличены до 15 / 50 / 100;
- добавлена детерминированная группировка полного каталога по repository, relation kind и schema/prefix;
- каждая группа содержит полный список sources, field count и явный признак полноты;
- dataset явно публикует `complete_source_catalog=true` и `complete_field_catalog=true`;
- standard/detailed prompt требует каждую source relation и все deterministically bound fields;
- основной текст называет не менее 20 sources и 30 concrete fields при наличии данных;
- большие каталоги переносятся в приложение D без потери элементов;
- unmapped/ambiguous usages по-прежнему не назначаются relation и не получают LLM-классификацию.

## Git Change Impact

- добавлен полный детерминированный grouped catalog изменённых файлов;
- по каждой группе публикуются все paths, counts, evidence IDs и признак полноты;
- добавлена сводка semantic deltas с counts, непустыми типами, total count и реальной полнотой delta artifacts;
- prompt требует показать каждый непустой table/column/relationship/lineage/transformation/flow/event-source delta;
- при изменении до 40 файлов показываются все paths;
- для больших изменений показываются все значимые paths, минимум 20 concrete files и полный остаток в приложении D;
- каждый deterministic risk signal объясняется через named file или delta;
- наличие изменённых tests/docs не выдаётся за успешное выполнение тестов.

## PDM

Отдельный `pdm-report/v1` не создан. Физическая модель остаётся частью канонического `data-model-report/v1` в режиме `physical_only`, где уже обязательны physical ER dataset и `erDiagram`. Это исключает параллельные контракты и дублирование логики отчёта модели данных.

## Доказательная дисциплина

Версия не добавляет SQL-эвристики, не интерпретирует unmapped fields и не повышает maturity Git deltas. Ограничения и отрицательные наблюдения остаются в приложениях A–C; полный крупный каталог может размещаться в приложении D.

## Тесты

- compileall: passed;
- targeted technical richness contracts: 8 passed, 2 skipped;
- full package suite: 86 passed, 16 skipped;
- skipped требуют внешних UCP/@900/Git artifacts; изменённые локальные контракты не пропущены.
