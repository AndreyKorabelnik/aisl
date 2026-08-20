# aisl-reporting 0.13.5

## Назначение

Версия вводит общую редакционную политику для всех семи стандартных LLM-отчётов. Отчёты должны сначала показывать подтверждённые знания, конкретные объекты, связи, операции и сценарии, а подробные ограничения переносить в приложения в конце.

## Основные изменения

### Общая редакционная политика

Добавлен общий resource `aisl_reporting/profiles/common/v1/editorial-policy.md`, который детерминированно включается перед профильным prompt.

Политика требует:

- начинать с подтверждённой картины, а не с disclaimers;
- сопровождать counts named examples;
- показывать probable/candidate/partial evidence с точным статусом;
- не скрывать извлечённые сведения из-за неполной доказательности;
- не заменять содержание рекомендацией обратиться к помощнику;
- размещать coverage, gaps, questions и provenance в приложениях A–C.

### Детерминированная структура prompt

`aisl_reporting.pipeline` теперь:

1. читает `report-contract.yaml` до рендера;
2. добавляет общую редакционную политику;
3. вставляет точный упорядоченный список обязательных заголовков текущего профиля;
4. добавляет профильный prompt;
5. оставляет явно выбранные instruction files последним блоком.

Для business-аудитории audience-specific opening (`О системе`) теперь располагается до общих обязательных разделов.

### Контракты всех отчётных профилей

Обновлены семь стандартных профилей:

- system description;
- data model;
- reference data;
- foreign data persistence;
- workspace interaction;
- SQL source inventory;
- git change impact.

Подробные ограничения перенесены в конец:

- `Приложение A. Полнота анализа и ограничения доказательности`;
- `Приложение B. Неоднозначности и вопросы для уточнения`;
- `Приложение C. Технические доказательства и provenance`.

### Отчёт по модели данных

Prompt модели данных теперь:

- требует раздел `ER-диаграммы` во всех непустых режимах;
- поддерживает physical-only ER по `physical_model_observations`;
- требует entity-only `erDiagram`, если relations не наблюдались;
- запрещает смешивать declared FK и observed SQL/JOOQ JOIN;
- требует показывать все доступные confirmed relationships при количестве до 30;
- усиливает требования к конкретным объектам, полям, ключам и связям.

Dataset builder в этой версии не расширялся: полнота physical ER всё ещё ограничена текущим bounded physical catalog. Это следующий отдельный шаг.

### Остальные профили

Профильные prompts усилены так, чтобы основная часть показывала:

- confirmed FDP mechanical cases и partial fragments;
- полный каталог кандидатов НСИ и concrete usage observations;
- все существенные git semantic deltas;
- полный SQL source inventory и usage patterns;
- system scenarios, boundaries, data/storage и architecture conclusions;
- workspace interactions и обязательные attribute journeys.

## Совместимость

Обратная совместимость с прежними обязательными заголовками не поддерживается. Старые отчёты не мигрируются. Новые отчёты валидируются по новой структуре приложений.

Conceptual Data Model artifact и SDD Draft package не затронуты: у них отдельные LLM pipelines и контракты.

## Тесты

- `compileall`: пройден;
- затронутые тесты: `34 passed`;
- полный набор AISL Reporting: `68 passed, 16 skipped`;
- skipped относятся только к отсутствующим внешним реальным UCP/@900/Git artifacts;
- wheel build без сетевой build isolation: пройден;
- общий editorial policy resource присутствует в wheel;
- 7 report contracts и 7 renderer prompts присутствуют в wheel.
