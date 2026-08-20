# Предварительный состав базы знаний: База знаний клиентского профиля

- Профиль: `client-workspace-knowledge`
- Область: `workspace:client-profile`
- Статус плана: `current_runtime_requires_boundary_migration`
- Fingerprint: `5ec1470e9d38c4f8d5f150a54627c3e2ab3e55d82677b2597baf6855f36e4d16`
- Фактическое наличие исходников: **ещё не проверялось**

## Что войдёт в базу знаний

### Модель данных, объявленная в коде

Типы, поля, объявленные связи и наследование, непосредственно наблюдаемые в исходном коде.

Добавлено в план: `required_dependency`; требуется для `effective-data-model, logical-physical-mapping`

Будут построены: типы и сущности, объявленные в коде; поля и их типы; объявленные связи между типами; наследование; покрытие, доказательства и пробелы анализа кода

Источники:
- **Объявления типов и полей в исходном коде** (обязательный) — `java-type-structure-evidence`; фактическая доступность: `not_assessed`
- **Пробелы evidence модели данных** (дополнительный) — `model-evidence-gap`; фактическая доступность: `not_assessed`

### Эффективное представление модели данных

Составное представление, связывающее независимо построенные модель из кода, физическую модель и доказанные логико-физические соответствия.

Добавлено в план: `user_requested`

Будут построены: слой модели, объявленной в коде; слой физической модели; доказанные логико-физические соответствия; составные домены и кластеры; необязательный контекст наблюдаемого SQL и storage usage; происхождение каждого объекта по слоям

Источники:
Зависимости от других моделей KLC:
- `code-declared-data-model` из `code-declared-data-model` (обязательная)
- `physical-data-model` из `physical-model` (обязательная)
- `logical-physical-model-mapping` из `logical-physical-mapping` (обязательная)
- `sql-observed-data-usage` из `sql-analysis` (дополнительная)
- `observed-storage-usage` из `observed-storage-usage` (дополнительная)

### Логико-физическое соответствие

Доказательные соответствия сущностей и атрибутов из кода таблицам, колонкам, ключам и связям физической модели.

Добавлено в план: `required_dependency`; требуется для `effective-data-model`

Будут построены: сущность → таблица; атрибут → колонка; ключ модели → физический ключ; связь модели → физическая связь; конфликты и неразрешённые соответствия

Источники:
- **Объявленные persistence mappings** (обязательный) — `java-persistence-mapping-evidence`; фактическая доступность: `not_assessed`
- **Наблюдаемое использование хранилищ** (дополнительный) — `storage-usage-evidence`; фактическая доступность: `not_assessed`
- **Пробелы evidence модели данных** (дополнительный) — `model-evidence-gap`; фактическая доступность: `not_assessed`
Зависимости от других моделей KLC:
- `code-declared-data-model` из `code-declared-data-model` (обязательная)
- `physical-data-model` из `physical-model` (обязательная)

### Физическая модель данных

Таблицы, колонки, ключи, ограничения, связи и пробелы предоставленной физической модели.

Добавлено в план: `required_dependency`; требуется для `effective-data-model, logical-physical-mapping`

Будут построены: таблицы; колонки; первичные и альтернативные ключи; внешние ключи и связи; ограничения; пробелы физической модели

Источники:
- **Предоставленная физическая модель** (обязательный) — `physical-model`; фактическая доступность: `not_assessed`

### Справочные данные

Наблюдаемые значения, записи литералов, кандидаты справочников и контекст использования.

Добавлено в план: `user_requested`

Будут построены: объявленные значения и перечисления; наблюдаемые литеральные записи; наборы значений; кандидаты справочников; контекст хранения и использования; неразрешённые альтернативы

Источники:
- **Объявленные значения и перечисления** (обязательный) — `declared-value-evidence`; фактическая доступность: `not_assessed`
- **Литеральные записи в хранилища и сообщения** (обязательный) — `literal-write-evidence`; фактическая доступность: `not_assessed`
- **Persistence mappings и операции** (дополнительный) — `java-persistence-evidence`; фактическая доступность: `not_assessed`
- **Потоки значений** (дополнительный) — `value-flow-evidence`; фактическая доступность: `not_assessed`
- **Входящие и исходящие интерфейсы** (дополнительный) — `interaction-boundary-evidence`; фактическая доступность: `not_assessed`
- **Конфигурация приложения** (дополнительный) — `configuration-evidence`; фактическая доступность: `not_assessed`

### SQL-инвентарь источников и назначений

SQL-операторы, таблицы, поля, роли использования, JOIN и доказательный source-to-target lineage.

Добавлено в план: `user_requested`

Будут построены: SQL-операторы и области видимости; таблицы-источники и назначения; используемые поля; роли полей: projection, join, filter и другие; JOIN и условия связи; source-to-target lineage; неразрешённые ссылки и покрытие

Источники:
- **SQL-код и его семантика** (обязательный) — `sql-analysis`; фактическая доступность: `not_assessed`
- **Предоставленная физическая модель** (дополнительный) — `physical-model`; фактическая доступность: `not_assessed`

### Взаимодействия систем и репозиториев

Подтверждённые и вероятные связи между входящими и исходящими интерфейсами.

Добавлено в план: `user_requested`

Будут построены: входящие и исходящие границы; протоколы и адреса; межрепозиторные взаимодействия; межсистемные взаимодействия; неоднозначные и неразрешённые сопоставления

Источники:
- **Входящие и исходящие интерфейсы** (обязательный) — `interaction-boundary-evidence`; фактическая доступность: `not_assessed`
- **Конфигурация приложения** (дополнительный) — `configuration-evidence`; фактическая доступность: `not_assessed`
- **Контекст выполнения и вызовов** (дополнительный) — `execution-context-evidence`; фактическая доступность: `not_assessed`

## Технический план

### KLC materializations

- `code-declared-data-model` для `code-declared-data-model` — `current_legacy`
- `effective-data-model` для `effective-data-model` — `current_legacy`
- `logical-physical-mapping` для `logical-physical-mapping` — `current_legacy`
- `physical-model` для `physical-data-model` — `current_typed`
- `reference-data` для `reference-data` — `current_legacy`
- `sql-analysis` для `sql-source-inventory` — `current_typed`
- `system-interactions` для `system-interactions` — `current_partial`

### Зависимости между моделями KLC

- `code-declared-data-model` / `code-declared-data-model/v1` из `code-declared-data-model`
- `logical-physical-model-mapping` / `logical-physical-model-mapping/v1` из `logical-physical-mapping`
- `observed-storage-usage` / `observed-storage-usage/v1` из `observed-storage-usage`
- `physical-data-model` / `knowledge_layer_physical_model/v1` из `physical-model`
- `sql-observed-data-usage` / `knowledge_layer_sql/v2` из `sql-analysis`

### Источники Core (расширенная диагностика)

- `config_scan` → Входящие и исходящие интерфейсы, Конфигурация приложения; знания: `reference-data, system-interactions`
- `declared_value_scan` → Объявленные значения и перечисления; знания: `reference-data`
- `declared_value_summary_scan` → Объявленные значения и перечисления; знания: `reference-data`
- `java_data_flow_build` → Потоки значений; знания: `reference-data`
- `java_data_model_lineage_build` → Литеральные записи в хранилища и сообщения, Пробелы evidence модели данных; знания: `code-declared-data-model, logical-physical-mapping, reference-data`
- `java_field_flow_build` → Потоки значений; знания: `reference-data`
- `java_persistence_lineage_build` → Persistence mappings и операции, Наблюдаемое использование хранилищ, Объявленные persistence mappings, Пробелы evidence модели данных; знания: `code-declared-data-model, logical-physical-mapping, reference-data`
- `java_source_observation_build` → Объявления типов и полей в исходном коде; знания: `code-declared-data-model`
- `java_structural_scan` → Persistence mappings и операции, Объявления типов и полей в исходном коде, Объявленные persistence mappings; знания: `code-declared-data-model, logical-physical-mapping, reference-data`
- `java_system_interaction_enrichment` → Входящие и исходящие интерфейсы; знания: `reference-data, system-interactions`
- `java_table_observation_build` → Persistence mappings и операции, Наблюдаемое использование хранилищ, Объявленные persistence mappings; знания: `logical-physical-mapping, reference-data`
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

- `info` `recommended_knowledge_dependencies_not_selected` — Selected knowledge remains in the plan; UI should explain that related knowledge can enrich or support it.
- `info` `source_availability_not_assessed` — This read-only resolution uses contracts only and does not inspect the selected repository/workspace.
- `warning` `target_evidence_boundary_not_current` — Знание может быть доступно через текущий runtime, но целевая цепочка typed evidence → KLC ещё требует миграции.
