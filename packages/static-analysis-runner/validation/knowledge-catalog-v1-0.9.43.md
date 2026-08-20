# Каталог знаний

- Схема: `knowledge_catalog/v1`
- Fingerprint: `d5a326626cbec3c3d66888475f77bb61642cc37d3ad89c9361edacda0b5763cd`
- Исполнение изменено: `none`

Пользователь выбирает знания и область repository/workspace. Core stages, analyzers, Task и Suite остаются внутренними техническими сущностями.

## Доступные виды знаний

### Происхождение и пути атрибутов (`attribute-lineage`)

Граф движения значений и доказательные пути атрибутов внутри и между репозиториями.

- Области: `workspace`
- Можно выбрать в knowledge_profile/v1: **да**
- Готовность: `current_legacy` — Materialization работает через текущий runtime, но зависит от Task/Profile или старого формата входов.
- KLC materialization: `repository-value-flow`
- В базу знаний войдут: локальные потоки значений; присваивания и передачи параметров; пути атрибутов; связи с хранилищами и интерфейсами; пробелы lineage
- Обязательные источники:
  - **Потоки значений** — `value-flow-evidence`; текущие Core stages: `java_data_flow_build, java_field_flow_build, java_traceability_build`; статус контракта: `proposed`
- Дополнительные источники:
  - **Persistence evidence** — `persistence-evidence`; текущие Core stages: `java_persistence_lineage_build, java_table_observation_build`; статус контракта: `proposed`
  - **Входящие и исходящие интерфейсы** — `interaction-boundary-evidence`; текущие Core stages: `java_system_interaction_enrichment, openapi_scan, config_scan`; статус контракта: `proposed`

### Концептуальная модель данных (`conceptual-data-model`)

Сущности, атрибуты, ключи, связи, наследование и логико-физические соответствия.

- Области: `repository, workspace`
- Можно выбрать в knowledge_profile/v1: **да**
- Готовность: `current_legacy` — Знание доступно через текущий legacy-путь; целевая KLC materialization по typed evidence ещё не реализована.
- KLC materialization: `conceptual-data-model`
- В базу знаний войдут: сущности; атрибуты и типы; ключи; связи и кратности; наследование; соответствия логических объектов таблицам и колонкам; покрытие, доказательства и пробелы
- Обязательные источники:
  - **Структура Java-кода** — `java-structure-evidence`; текущие Core stages: `java_structural_scan, java_source_observation_build`; статус контракта: `proposed`
  - **Persistence mappings и операции** — `java-persistence-evidence`; текущие Core stages: `java_persistence_lineage_build, java_table_observation_build, java_structural_scan`; статус контракта: `proposed`
  - **Преобразования, builder и присваивания** — `java-mapping-evidence`; текущие Core stages: `java_structural_scan, java_data_model_lineage_build`; статус контракта: `proposed`
- Дополнительные источники:
  - **Физическая схема из репозитория** — `physical-schema-evidence`; текущие Core stages: `db_schema_scan`; статус контракта: `proposed`
  - **Наблюдения таблиц, ключей и связей** — `table-observation-evidence`; текущие Core stages: `java_table_observation_build`; статус контракта: `proposed`
  - **Объявленные значения и перечисления** — `declared-value-evidence`; текущие Core stages: `declared_value_scan, declared_value_summary_scan`; статус контракта: `proposed`

### Покрытие анализа взаимодействий (`interaction-coverage`)

Покрытие и диагностика входящих и исходящих интерфейсов по репозиториям.

- Области: `workspace`
- Можно выбрать в knowledge_profile/v1: **да**
- Готовность: `current_partial` — Materialization работает, но целевая evidence-граница ещё неполна.
- KLC materialization: `interaction-coverage`
- В базу знаний войдут: покрытие интерфейсов; неразрешённые границы; неоднозначные сопоставления; диагностика по репозиториям
- Обязательные источники:
  - **Входящие и исходящие интерфейсы** — `interaction-boundary-evidence`; текущие Core stages: `java_system_interaction_enrichment, openapi_scan, config_scan`; статус контракта: `proposed`

### Контракты полей во взаимодействиях (`interaction-field-contracts`)

Связи полей и атрибутов на сопоставленных межсистемных взаимодействиях.

- Области: `workspace`
- Можно выбрать в knowledge_profile/v1: **да**
- Готовность: `current_partial` — Materialization работает, но целевая evidence-граница ещё неполна.
- KLC materialization: `interaction-field-contracts`
- В базу знаний войдут: поля входящих и исходящих сообщений; сопоставления полей; пути атрибутов через границы систем; пробелы и неоднозначности полевых контрактов
- Обязательные источники:
  - **Граф потоков значений репозитория** — `repository-value-flow`; текущие Core stages: `не Core / ещё не определено`; статус контракта: `current_output`
  - **Сопоставленные взаимодействия репозиториев** — `repository-interaction-evidence`; текущие Core stages: `не Core / ещё не определено`; статус контракта: `current_output`

### Острова взаимодействующих репозиториев (`interaction-islands`)

Связные группы репозиториев по подтверждённым и вероятным взаимодействиям.

- Области: `workspace`
- Можно выбрать в knowledge_profile/v1: **да**
- Готовность: `current_partial` — Materialization работает, но целевая evidence-граница ещё неполна.
- KLC materialization: `interaction-islands`
- В базу знаний войдут: строгие острова; расширенные острова; изолированные репозитории; состав и покрытие островов
- Обязательные источники:
  - **Сопоставленные взаимодействия репозиториев** — `repository-interaction-evidence`; текущие Core stages: `не Core / ещё не определено`; статус контракта: `current_output`
- Дополнительные источники:
  - **Покрытие взаимодействий** — `interaction-coverage`; текущие Core stages: `не Core / ещё не определено`; статус контракта: `current_output`

### Физическая модель данных (`physical-data-model`)

Таблицы, колонки, ключи, ограничения, связи и пробелы предоставленной физической модели.

- Области: `repository, workspace`
- Можно выбрать в knowledge_profile/v1: **да**
- Готовность: `current_typed` — Materialization уже использует самостоятельный типизированный вход.
- KLC materialization: `physical-model`
- В базу знаний войдут: таблицы; колонки; первичные и альтернативные ключи; внешние ключи и связи; ограничения; пробелы физической модели
- Обязательные источники:
  - **Предоставленная физическая модель** — `physical-model`; текущие Core stages: `не Core / ещё не определено`; статус контракта: `current`

### Топология портфеля репозиториев (`portfolio-topology`)

Компактная топология и острова взаимодействий большого портфеля репозиториев.

- Области: `portfolio`
- Можно выбрать в knowledge_profile/v1: **нет**
- Готовность: `current_legacy` — Materialization работает через текущий runtime, но зависит от Task/Profile или старого формата входов.
- KLC materialization: `portfolio-topology`
- В базу знаний войдут: репозитории; границы взаимодействий; рёбра топологии; острова; покрытие
- Обязательные источники:
  - **Компактный каталог интерфейсов репозитория** — `repository-interface-catalog-evidence`; текущие Core stages: `java_system_interaction_enrichment, openapi_scan`; статус контракта: `proposed`
- Дополнительные источники:
  - **Метаданные репозитория и системы** — `repository-metadata`; текущие Core stages: `не Core / ещё не определено`; статус контракта: `proposed`

### Справочные данные (`reference-data`)

Наблюдаемые значения, записи литералов, кандидаты справочников и контекст использования.

- Области: `repository, workspace`
- Можно выбрать в knowledge_profile/v1: **да**
- Готовность: `current_legacy` — Знание доступно через текущий legacy-путь; целевая KLC materialization по typed evidence ещё не реализована.
- KLC materialization: `reference-data`
- В базу знаний войдут: объявленные значения и перечисления; наблюдаемые литеральные записи; наборы значений; кандидаты справочников; контекст хранения и использования; неразрешённые альтернативы
- Обязательные источники:
  - **Объявленные значения и перечисления** — `declared-value-evidence`; текущие Core stages: `declared_value_scan, declared_value_summary_scan`; статус контракта: `proposed`
  - **Литеральные записи в хранилища и сообщения** — `literal-write-evidence`; текущие Core stages: `java_data_model_lineage_build, reference_data_fact_base`; статус контракта: `proposed`
- Дополнительные источники:
  - **Persistence mappings и операции** — `java-persistence-evidence`; текущие Core stages: `java_persistence_lineage_build, java_table_observation_build, java_structural_scan`; статус контракта: `proposed`
  - **Потоки значений** — `value-flow-evidence`; текущие Core stages: `java_data_flow_build, java_field_flow_build, java_traceability_build`; статус контракта: `proposed`
  - **Входящие и исходящие интерфейсы** — `interaction-boundary-evidence`; текущие Core stages: `java_system_interaction_enrichment, openapi_scan, config_scan`; статус контракта: `proposed`
  - **Конфигурация приложения** — `configuration-evidence`; текущие Core stages: `config_scan`; статус контракта: `proposed`

### SQL-инвентарь источников и назначений (`sql-source-inventory`)

SQL-операторы, таблицы, поля, роли использования, JOIN и доказательный source-to-target lineage.

- Области: `repository, workspace`
- Можно выбрать в knowledge_profile/v1: **да**
- Готовность: `current_typed` — Materialization уже использует самостоятельный типизированный вход.
- KLC materialization: `sql-analysis`
- В базу знаний войдут: SQL-операторы и области видимости; таблицы-источники и назначения; используемые поля; роли полей: projection, join, filter и другие; JOIN и условия связи; source-to-target lineage; неразрешённые ссылки и покрытие
- Обязательные источники:
  - **SQL-код и его семантика** — `sql-analysis`; текущие Core stages: `sql_scan, sql_script_structure_scan, sql_script_semantic_inventory, sql_scoped_relation_scan, sql_scoped_column_usage_scan, sql_scoped_projection_scan, sql_scoped_direct_lineage_build, sql_scoped_write_target_binding, sql_join_graph_scan, sql_column_lineage_scan, sql_source_usage_scan, sql_mart_inventory_scan, sql_mart_lineage_gap_build`; статус контракта: `current`
- Дополнительные источники:
  - **Предоставленная физическая модель** — `physical-model`; текущие Core stages: `не Core / ещё не определено`; статус контракта: `current`

### Описание системы (`system-description`)

Сценарии, внешние зависимости, хранилища, источники данных и границы доступа.

- Области: `repository, workspace`
- Можно выбрать в knowledge_profile/v1: **да**
- Готовность: `current_legacy` — Знание доступно через текущий legacy-путь; целевая KLC materialization по typed evidence ещё не реализована.
- KLC materialization: `system-description`
- В базу знаний войдут: системные сценарии; внешние зависимости; используемые хранилища; источники данных; границы доступа; покрытие и пробелы
- Обязательные источники:
  - **Входящие и исходящие интерфейсы** — `interaction-boundary-evidence`; текущие Core stages: `java_system_interaction_enrichment, openapi_scan, config_scan`; статус контракта: `proposed`
  - **Конфигурация приложения** — `configuration-evidence`; текущие Core stages: `config_scan`; статус контракта: `proposed`
  - **Зависимости сборки** — `build-dependency-evidence`; текущие Core stages: `maven_dependency_scan, gradle_dependency_scan`; статус контракта: `proposed`
  - **Доступ к хранилищам** — `storage-access-evidence`; текущие Core stages: `java_persistence_lineage_build, java_table_observation_build, java_data_model_lineage_build`; статус контракта: `proposed`
- Дополнительные источники:
  - **Потоки значений** — `value-flow-evidence`; текущие Core stages: `java_data_flow_build, java_field_flow_build, java_traceability_build`; статус контракта: `proposed`
  - **Физическая схема из репозитория** — `physical-schema-evidence`; текущие Core stages: `db_schema_scan`; статус контракта: `proposed`

### Взаимодействия систем и репозиториев (`system-interactions`)

Подтверждённые и вероятные связи между входящими и исходящими интерфейсами.

- Области: `workspace`
- Можно выбрать в knowledge_profile/v1: **да**
- Готовность: `current_partial` — Materialization работает, но целевая evidence-граница ещё неполна.
- KLC materialization: `system-interactions`
- В базу знаний войдут: входящие и исходящие границы; протоколы и адреса; межрепозиторные взаимодействия; межсистемные взаимодействия; неоднозначные и неразрешённые сопоставления
- Обязательные источники:
  - **Входящие и исходящие интерфейсы** — `interaction-boundary-evidence`; текущие Core stages: `java_system_interaction_enrichment, openapi_scan, config_scan`; статус контракта: `proposed`
- Дополнительные источники:
  - **Конфигурация приложения** — `configuration-evidence`; текущие Core stages: `config_scan`; статус контракта: `proposed`
  - **Контекст выполнения и вызовов** — `execution-context-evidence`; текущие Core stages: `java_traceability_build`; статус контракта: `proposed`

### Общий SQL-каталог workspace (`workspace-sql-source-inventory`)

Агрегированный каталог SQL-витрин, источников и назначений нескольких репозиториев.

- Области: `workspace`
- Можно выбрать в knowledge_profile/v1: **да**
- Готовность: `current_legacy` — Знание доступно через текущий legacy-путь; целевая KLC materialization по typed evidence ещё не реализована.
- KLC materialization: `workspace-sql-mart-catalog`
- В базу знаний войдут: SQL-витрины workspace; общий инвентарь таблиц и полей; источники и назначения по репозиториям; межрепозиторные соответствия; покрытие и пробелы
- Обязательные источники:
  - **SQL-код и его семантика** — `sql-analysis`; текущие Core stages: `sql_scan, sql_script_structure_scan, sql_script_semantic_inventory, sql_scoped_relation_scan, sql_scoped_column_usage_scan, sql_scoped_projection_scan, sql_scoped_direct_lineage_build, sql_scoped_write_target_binding, sql_join_graph_scan, sql_column_lineage_scan, sql_source_usage_scan, sql_mart_inventory_scan, sql_mart_lineage_gap_build`; статус контракта: `current`
- Дополнительные источники:
  - **Предоставленная физическая модель** — `physical-model`; текущие Core stages: `не Core / ещё не определено`; статус контракта: `current`
  - **Метаданные репозитория и системы** — `repository-metadata`; текущие Core stages: `не Core / ещё не определено`; статус контракта: `proposed`

## Внутренние materializations

- `common-data-model` — Текущий технический мост; пользовательский вид знания — conceptual-data-model.
- `suite-evidence-registry` — Технический реестр выполнения и артефактов, а не самостоятельное бизнес-знание.

## Следующий шаг

`conceptual_model_evidence_sufficiency/v1_after_user_facing_contract_validation`
