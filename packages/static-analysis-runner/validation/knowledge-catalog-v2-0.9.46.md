# Каталог знаний

- Схема: `knowledge_catalog/v2`
- Fingerprint: `3aae461fe16bb1b7ea6f85a907321e0acba36ba3e1efd658b42e911d2790dea1`
- Исполнение изменено: `none`

Пользователь выбирает знания и область repository/workspace. Core stages, analyzers, Task и Suite остаются внутренними техническими сущностями.

## Доступные виды знаний

### Происхождение и пути атрибутов (`attribute-lineage`)

Граф движения значений и доказательные пути атрибутов внутри и между репозиториями.

- Области: `workspace`
- Можно выбрать в knowledge_profile/v2: **да**
- Готовность: `current_legacy` — Materialization работает через текущий runtime, но зависит от Task/Profile или старого формата входов.
- KLC materialization: `repository-value-flow`
- В базу знаний войдут: локальные потоки значений; присваивания и передачи параметров; пути атрибутов; связи с хранилищами и интерфейсами; пробелы lineage
- Обязательные источники:
  - **Потоки значений** — `value-flow-evidence`; текущие Core stages: `java_data_flow_build, java_field_flow_build, java_traceability_build`; статус контракта: `proposed`
- Дополнительные источники:
  - **Persistence evidence** — `persistence-evidence`; текущие Core stages: `java_persistence_lineage_build, java_table_observation_build`; статус контракта: `proposed`
  - **Входящие и исходящие интерфейсы** — `interaction-boundary-evidence`; текущие Core stages: `java_system_interaction_enrichment, openapi_scan, config_scan`; статус контракта: `proposed`

### Модель данных, объявленная в коде (`code-declared-data-model`)

Типы, поля, объявленные связи и наследование, непосредственно наблюдаемые в исходном коде.

- Области: `repository, workspace`
- Можно выбрать в knowledge_profile/v2: **да**
- Готовность: `current_legacy` — Знание доступно через текущий legacy-путь; целевая KLC materialization по typed evidence ещё не реализована.
- KLC materialization: `code-declared-data-model`
- В базу знаний войдут: типы и сущности, объявленные в коде; поля и их типы; объявленные связи между типами; наследование; покрытие, доказательства и пробелы анализа кода
- Обязательные источники:
  - **Объявления типов и полей в исходном коде** — `java-type-structure-evidence`; текущие Core stages: `java_structural_scan, java_source_observation_build`; статус контракта: `proposed`
- Дополнительные источники:
  - **Пробелы evidence модели данных** — `model-evidence-gap`; текущие Core stages: `java_data_model_lineage_build, java_persistence_lineage_build`; статус контракта: `proposed`

### Эффективное представление модели данных (`effective-data-model`)

Составное представление, связывающее независимо построенные модель из кода, физическую модель и доказанные логико-физические соответствия.

- Области: `repository, workspace`
- Можно выбрать в knowledge_profile/v2: **да**
- Готовность: `current_legacy` — Знание доступно через текущий legacy-путь; целевая KLC materialization по typed evidence ещё не реализована.
- KLC materialization: `effective-data-model`
- В базу знаний войдут: слой модели, объявленной в коде; слой физической модели; доказанные логико-физические соответствия; составные домены и кластеры; необязательный контекст наблюдаемого SQL и storage usage; происхождение каждого объекта по слоям
- Обязательные источники:
- Обязательные знания: `code-declared-data-model`, `logical-physical-mapping`, `physical-data-model`
- Рекомендуемые знания: `observed-storage-usage`, `sql-source-inventory`
- Обязательные модели KLC:
  - `code-declared-data-model` из `code-declared-data-model`
  - `physical-data-model` из `physical-model`
  - `logical-physical-model-mapping` из `logical-physical-mapping`
- Дополнительные модели KLC:
  - `sql-observed-data-usage` из `sql-analysis`
  - `observed-storage-usage` из `observed-storage-usage`

### Покрытие анализа взаимодействий (`interaction-coverage`)

Покрытие и диагностика входящих и исходящих интерфейсов по репозиториям.

- Области: `workspace`
- Можно выбрать в knowledge_profile/v2: **да**
- Готовность: `current_partial` — Materialization работает, но целевая evidence-граница ещё неполна.
- KLC materialization: `interaction-coverage`
- В базу знаний войдут: покрытие интерфейсов; неразрешённые границы; неоднозначные сопоставления; диагностика по репозиториям
- Обязательные источники:
  - **Входящие и исходящие интерфейсы** — `interaction-boundary-evidence`; текущие Core stages: `java_system_interaction_enrichment, openapi_scan, config_scan`; статус контракта: `proposed`

### Контракты полей во взаимодействиях (`interaction-field-contracts`)

Связи полей и атрибутов на сопоставленных межсистемных взаимодействиях.

- Области: `workspace`
- Можно выбрать в knowledge_profile/v2: **да**
- Готовность: `current_partial` — Materialization работает, но целевая evidence-граница ещё неполна.
- KLC materialization: `interaction-field-contracts`
- В базу знаний войдут: поля входящих и исходящих сообщений; сопоставления полей; пути атрибутов через границы систем; пробелы и неоднозначности полевых контрактов
- Обязательные источники:
  - **Граф потоков значений репозитория** — `repository-value-flow`; текущие Core stages: `не Core / ещё не определено`; статус контракта: `current_output`
  - **Сопоставленные взаимодействия репозиториев** — `repository-interaction-evidence`; текущие Core stages: `не Core / ещё не определено`; статус контракта: `current_output`
- Рекомендуемые знания: `attribute-lineage`, `system-interactions`

### Острова взаимодействующих репозиториев (`interaction-islands`)

Связные группы репозиториев по подтверждённым и вероятным взаимодействиям.

- Области: `workspace`
- Можно выбрать в knowledge_profile/v2: **да**
- Готовность: `current_partial` — Materialization работает, но целевая evidence-граница ещё неполна.
- KLC materialization: `interaction-islands`
- В базу знаний войдут: строгие острова; расширенные острова; изолированные репозитории; состав и покрытие островов
- Обязательные источники:
  - **Сопоставленные взаимодействия репозиториев** — `repository-interaction-evidence`; текущие Core stages: `не Core / ещё не определено`; статус контракта: `current_output`
- Рекомендуемые знания: `system-interactions`
- Дополнительные источники:
  - **Покрытие взаимодействий** — `interaction-coverage`; текущие Core stages: `не Core / ещё не определено`; статус контракта: `current_output`

### Логико-физическое соответствие (`logical-physical-mapping`)

Доказательные соответствия сущностей и атрибутов из кода таблицам, колонкам, ключам и связям физической модели.

- Области: `repository, workspace`
- Можно выбрать в knowledge_profile/v2: **да**
- Готовность: `current_legacy` — Знание доступно через текущий legacy-путь; целевая KLC materialization по typed evidence ещё не реализована.
- KLC materialization: `logical-physical-mapping`
- В базу знаний войдут: сущность → таблица; атрибут → колонка; ключ модели → физический ключ; связь модели → физическая связь; конфликты и неразрешённые соответствия
- Обязательные источники:
  - **Объявленные persistence mappings** — `java-persistence-mapping-evidence`; текущие Core stages: `java_persistence_lineage_build, java_table_observation_build, java_structural_scan`; статус контракта: `proposed`
- Обязательные знания: `code-declared-data-model`, `physical-data-model`
- Обязательные модели KLC:
  - `code-declared-data-model` из `code-declared-data-model`
  - `physical-data-model` из `physical-model`
- Дополнительные источники:
  - **Наблюдаемое использование хранилищ** — `storage-usage-evidence`; текущие Core stages: `java_persistence_lineage_build, java_table_observation_build`; статус контракта: `proposed`
  - **Пробелы evidence модели данных** — `model-evidence-gap`; текущие Core stages: `java_data_model_lineage_build, java_persistence_lineage_build`; статус контракта: `proposed`

### Наблюдаемое использование хранилищ (`observed-storage-usage`)

Фактически наблюдаемые чтения, записи и обращения к объектам хранения из кода.

- Области: `repository, workspace`
- Можно выбрать в knowledge_profile/v2: **да**
- Готовность: `current_legacy` — Знание доступно через текущий legacy-путь; целевая KLC materialization по typed evidence ещё не реализована.
- KLC materialization: `observed-storage-usage`
- В базу знаний войдут: чтения из хранилищ; записи в хранилища; используемые таблицы, коллекции и поля; точки доступа в коде; неразрешённые цели хранения
- Обязательные источники:
  - **Наблюдаемое использование хранилищ** — `storage-usage-evidence`; текущие Core stages: `java_persistence_lineage_build, java_table_observation_build`; статус контракта: `proposed`
- Рекомендуемые знания: `code-declared-data-model`, `physical-data-model`
- Дополнительные модели KLC:
  - `code-declared-data-model` из `code-declared-data-model`
  - `physical-data-model` из `physical-model`
- Дополнительные источники:
  - **Пробелы evidence модели данных** — `model-evidence-gap`; текущие Core stages: `java_data_model_lineage_build, java_persistence_lineage_build`; статус контракта: `proposed`

### Физическая модель данных (`physical-data-model`)

Таблицы, колонки, ключи, ограничения, связи и пробелы предоставленной физической модели.

- Области: `repository, workspace`
- Можно выбрать в knowledge_profile/v2: **да**
- Готовность: `current_typed` — Materialization уже использует самостоятельный типизированный вход.
- KLC materialization: `physical-model`
- В базу знаний войдут: таблицы; колонки; первичные и альтернативные ключи; внешние ключи и связи; ограничения; пробелы физической модели
- Обязательные источники:
  - **Предоставленная физическая модель** — `physical-model`; текущие Core stages: `не Core / ещё не определено`; статус контракта: `current`

### Топология портфеля репозиториев (`portfolio-topology`)

Компактная топология и острова взаимодействий большого портфеля репозиториев.

- Области: `portfolio`
- Можно выбрать в knowledge_profile/v2: **нет**
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
- Можно выбрать в knowledge_profile/v2: **да**
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
- Можно выбрать в knowledge_profile/v2: **да**
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
- Можно выбрать в knowledge_profile/v2: **да**
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
- Можно выбрать в knowledge_profile/v2: **да**
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
- Можно выбрать в knowledge_profile/v2: **да**
- Готовность: `current_legacy` — Знание доступно через текущий legacy-путь; целевая KLC materialization по typed evidence ещё не реализована.
- KLC materialization: `workspace-sql-mart-catalog`
- В базу знаний войдут: SQL-витрины workspace; общий инвентарь таблиц и полей; источники и назначения по репозиториям; межрепозиторные соответствия; покрытие и пробелы
- Обязательные источники:
  - **SQL-код и его семантика** — `sql-analysis`; текущие Core stages: `sql_scan, sql_script_structure_scan, sql_script_semantic_inventory, sql_scoped_relation_scan, sql_scoped_column_usage_scan, sql_scoped_projection_scan, sql_scoped_direct_lineage_build, sql_scoped_write_target_binding, sql_join_graph_scan, sql_column_lineage_scan, sql_source_usage_scan, sql_mart_inventory_scan, sql_mart_lineage_gap_build`; статус контракта: `current`
- Рекомендуемые знания: `sql-source-inventory`
- Дополнительные источники:
  - **Предоставленная физическая модель** — `physical-model`; текущие Core stages: `не Core / ещё не определено`; статус контракта: `current`
  - **Метаданные репозитория и системы** — `repository-metadata`; текущие Core stages: `не Core / ещё не определено`; статус контракта: `proposed`

## Внутренние materializations

- `common-data-model` — Текущий legacy umbrella; заменяется отдельными code-declared, physical, mapping, observed-usage и effective знаниями.
- `suite-evidence-registry` — Технический реестр выполнения и артефактов, а не самостоятельное бизнес-знание.

## Следующий шаг

`generic_knowledge_architecture_audit/v1_for_code-declared-data-model`
