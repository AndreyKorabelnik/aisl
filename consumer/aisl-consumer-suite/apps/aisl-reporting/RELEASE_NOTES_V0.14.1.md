# aisl-reporting 0.14.1

## Назначение

Версия устраняет зависимость корректности ER-диаграмм от Mermaid-кода, сформированного LLM. Для профиля `data-model-report/v1` Reporting теперь детерминированно строит Mermaid из уже валидированного diagram dataset и заменяет только раздел `## ER-диаграммы` после основного LLM-rendering.

## Что изменено

- добавлен генератор `deterministic-data-model-mermaid/v1`;
- логическая ER строится из `sections.diagrams.logical_er`;
- физическая ER строится из `sections.diagrams.physical_er`;
- observed SQL/JOOQ relations строятся отдельным `flowchart` из `sections.diagrams.observed_usage`;
- declared FK и observed JOIN не смешиваются;
- Mermaid entity identifiers формируются детерминированно и не зависят от имён таблиц;
- типы, имена атрибутов и подписи очищаются от Mermaid-разделителей;
- точные имена объектов сохраняются в явном сопоставлении под диаграммой;
- в физической ER используются консервативные кардинальности, если nullable/unique не доказаны dataset;
- исходный текст отчёта вне ER-раздела не изменяется;
- второй LLM correction pass остаётся только аварийным fallback, если детерминированный слой неприменим или validation всё ещё сообщает об отсутствующей ER.

## Почему исправление сделано в Reporting

Структурированный ER dataset уже является каноническим источником диаграммы. LLM должна объяснять модель и формировать повествовательную часть, но не должна повторно сериализовать доказанные сущности и связи в чувствительный к синтаксису Mermaid DSL.

## Обратная совместимость

Compatibility adapter не добавлялся. Формат report dataset не изменён; изменился финальный renderer pipeline для `data-model-report/v1`.

## Тесты

- compileall: passed;
- targeted deterministic ER / validation / correction / Mermaid normalization: 26 passed;
- full package suite: 92 passed, 16 skipped;
- regression dataset: deterministic physical ER and observed-usage Mermaid generated successfully.
