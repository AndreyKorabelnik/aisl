# aisl-reporting 0.15.0

## Основное изменение

Reporting переведён с прямого чтения объединённой `knowledge-layer.duckdb` на ревизии Knowledge API 0.16.0.

## Добавлено

- источник `KnowledgeApiRevision`;
- разрешение активной или явно заданной ревизии;
- выбор knowledge artifact по `model_kind` и обязательным capabilities;
- provenance выбранной ревизии и артефакта в dataset и run manifest;
- API-проекция data-model report через effective/physical endpoints;
- поддержка удалённых artifact URI для API-проекционных профилей;
- строгие ошибки при отсутствии требуемого знания или неоднозначном наборе артефактов.

## Удалено без совместимости

- `input_kind=knowledge_layer`;
- прямой `--input-artifact knowledge-layer.duckdb` для knowledge-профилей;
- публичные `artifact-*` и `package-*` команды;
- conceptual-data-model artifact pipeline внутри Reporting;
- SDD draft package pipeline внутри Reporting;
- устаревшие fixture-тесты общей DuckDB.

## Data model report

- логическая часть читается из `effective-data-model`;
- физическая часть читается отдельно при capability `common.physical-model`;
- observed usage не смешивается с declared physical relationships;
- Mermaid ER формируется детерминированно.

## Совместимость

Обратная совместимость не предоставляется. Для knowledge-профилей требуется Knowledge API revision.
