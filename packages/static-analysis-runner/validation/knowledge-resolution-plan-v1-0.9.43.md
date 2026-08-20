# Предварительный состав базы знаний: База знаний клиентского профиля

- Профиль: `client-workspace-knowledge`
- Область: `workspace:client-profile`
- Статус плана: `current_runtime_requires_boundary_migration`
- Fingerprint: `4fb8d21021f100515b20bfb1b095e28e13e1930c91ff3976d91f54c7673579b0`
- Фактическое наличие исходников: **ещё не проверялось**

## Что войдёт в базу знаний

### Концептуальная модель данных

Сущности, атрибуты, ключи, связи, наследование и логико-физические соответствия.

Будут построены: сущности; атрибуты и типы; ключи; связи и кратности; наследование; соответствия логических объектов таблицам и колонкам; покрытие, доказательства и пробелы

Источники:
- **Структура Java-кода** (обязательный) — `java-structure-evidence`; фактическая доступность: `not_assessed`
- **Persistence mappings и операции** (обязательный) — `java-persistence-evidence`; фактическая доступность: `not_assessed`
- **Преобразования, builder и присваивания** (обязательный) — `java-mapping-evidence`; фактическая доступность: `not_assessed`
- **Физическая схема из репозитория** (дополнительный) — `physical-schema-evidence`; фактическая доступность: `not_assessed`
- **Наблюдения таблиц, ключей и связей** (дополнительный) — `table-observation-evidence`; фактическая доступность: `not_assessed`
- **Объявленные значения и перечисления** (дополнительный) — `declared-value-evidence`; фактическая доступность: `not_assessed`

### SQL-инвентарь источников и назначений

SQL-операторы, таблицы, поля, роли использования, JOIN и доказательный source-to-target lineage.

Будут построены: SQL-операторы и области видимости; таблицы-источники и назначения; используемые поля; роли полей: projection, join, filter и другие; JOIN и условия связи; source-to-target lineage; неразрешённые ссылки и покрытие

Источники:
- **SQL-код и его семантика** (обязательный) — `sql-analysis`; фактическая доступность: `not_assessed`
- **Предоставленная физическая модель** (дополнительный) — `physical-model`; фактическая доступность: `not_assessed`

### Взаимодействия систем и репозиториев

Подтверждённые и вероятные связи между входящими и исходящими интерфейсами.

Будут построены: входящие и исходящие границы; протоколы и адреса; межрепозиторные взаимодействия; межсистемные взаимодействия; неоднозначные и неразрешённые сопоставления

Источники:
- **Входящие и исходящие интерфейсы** (обязательный) — `interaction-boundary-evidence`; фактическая доступность: `not_assessed`
- **Конфигурация приложения** (дополнительный) — `configuration-evidence`; фактическая доступность: `not_assessed`
- **Контекст выполнения и вызовов** (дополнительный) — `execution-context-evidence`; фактическая доступность: `not_assessed`

### Справочные данные

Наблюдаемые значения, записи литералов, кандидаты справочников и контекст использования.

Будут построены: объявленные значения и перечисления; наблюдаемые литеральные записи; наборы значений; кандидаты справочников; контекст хранения и использования; неразрешённые альтернативы

Источники:
- **Объявленные значения и перечисления** (обязательный) — `declared-value-evidence`; фактическая доступность: `not_assessed`
- **Литеральные записи в хранилища и сообщения** (обязательный) — `literal-write-evidence`; фактическая доступность: `not_assessed`
- **Persistence mappings и операции** (дополнительный) — `java-persistence-evidence`; фактическая доступность: `not_assessed`
- **Потоки значений** (дополнительный) — `value-flow-evidence`; фактическая доступность: `not_assessed`
- **Входящие и исходящие интерфейсы** (дополнительный) — `interaction-boundary-evidence`; фактическая доступность: `not_assessed`
- **Конфигурация приложения** (дополнительный) — `configuration-evidence`; фактическая доступность: `not_assessed`

## Технический план

### KLC materializations

- `conceptual-data-model` для `conceptual-data-model` — `current_legacy`
- `reference-data` для `reference-data` — `current_legacy`
- `sql-analysis` для `sql-source-inventory` — `current_typed`
- `system-interactions` для `system-interactions` — `current_partial`

### Источники Core (расширенная диагностика)

- `config_scan` → Входящие и исходящие интерфейсы, Конфигурация приложения; знания: `reference-data, system-interactions`
- `db_schema_scan` → Физическая схема из репозитория; знания: `conceptual-data-model`
- `declared_value_scan` → Объявленные значения и перечисления; знания: `conceptual-data-model, reference-data`
- `declared_value_summary_scan` → Объявленные значения и перечисления; знания: `conceptual-data-model, reference-data`
- `java_data_flow_build` → Потоки значений; знания: `reference-data`
- `java_data_model_lineage_build` → Литеральные записи в хранилища и сообщения, Преобразования, builder и присваивания; знания: `conceptual-data-model, reference-data`
- `java_field_flow_build` → Потоки значений; знания: `reference-data`
- `java_persistence_lineage_build` → Persistence mappings и операции; знания: `conceptual-data-model, reference-data`
- `java_source_observation_build` → Структура Java-кода; знания: `conceptual-data-model`
- `java_structural_scan` → Persistence mappings и операции, Преобразования, builder и присваивания, Структура Java-кода; знания: `conceptual-data-model, reference-data`
- `java_system_interaction_enrichment` → Входящие и исходящие интерфейсы; знания: `reference-data, system-interactions`
- `java_table_observation_build` → Persistence mappings и операции, Наблюдения таблиц, ключей и связей; знания: `conceptual-data-model, reference-data`
- `java_traceability_build` → Контекст выполнения и вызовов, Потоки значений; знания: `reference-data, system-interactions`
- `openapi_scan` → Входящие и исходящие интерфейсы; знания: `reference-data, system-interactions`
- `reference_data_fact_base` → Литеральные записи в хранилища и сообщения; знания: `reference-data`
- `sql_column_lineage_scan` → SQL-код и его семантика; знания: `sql-source-inventory`
- `sql_join_graph_scan` → SQL-код и его семантика; знания: `sql-source-inventory`
- `sql_mart_inventory_scan` → SQL-код и его семантика; знания: `sql-source-inventory`
- `sql_mart_lineage_gap_build` → SQL-код и его семантика; знания: `sql-source-inventory`
- `sql_scan` → SQL-код и его семантика; знания: `sql-source-inventory`
- `sql_scoped_column_usage_scan` → SQL-код и его семантика; знания: `sql-source-inventory`
- `sql_scoped_direct_lineage_build` → SQL-код и его семантика; знания: `sql-source-inventory`
- `sql_scoped_projection_scan` → SQL-код и его семантика; знания: `sql-source-inventory`
- `sql_scoped_relation_scan` → SQL-код и его семантика; знания: `sql-source-inventory`
- `sql_scoped_write_target_binding` → SQL-код и его семантика; знания: `sql-source-inventory`
- `sql_script_semantic_inventory` → SQL-код и его семантика; знания: `sql-source-inventory`
- `sql_script_structure_scan` → SQL-код и его семантика; знания: `sql-source-inventory`
- `sql_source_usage_scan` → SQL-код и его семантика; знания: `sql-source-inventory`

### Foundation

`call-index`, `configuration-index`, `java-structure-index`, `openapi-index`, `physical-schema-index`, `repository-file-index`, `sql-parse-index`, `symbol-and-type-index`

## Диагностика

- `info` `source_availability_not_assessed` — This read-only resolution uses contracts only and does not inspect the selected repository/workspace.
- `warning` `target_evidence_boundary_not_current` — Знание может быть доступно через текущий runtime, но целевая цепочка typed evidence → KLC ещё требует миграции.
