# Каталог знаний

- Схема: `knowledge_catalog/v2`
- Fingerprint: `e7463b8df9bb99cc123848e720924a0c41b488d7e5d146b03be146394dbf64ac`
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
  - **value-flow-evidence** — `value-flow-evidence`; producer/analyzer: `внешний/не зарегистрирован`; статус: `not_applicable`
- Дополнительные источники:
  - **persistence-evidence** — `persistence-evidence`; producer/analyzer: `внешний/не зарегистрирован`; статус: `not_applicable`
  - **interaction-boundary-evidence** — `interaction-boundary-evidence`; producer/analyzer: `внешний/не зарегистрирован`; статус: `not_applicable`

### Модель данных, объявленная в коде (`code-declared-data-model`)

Типы, поля, объявленные связи и наследование, непосредственно наблюдаемые в исходном коде.

- Области: `repository, workspace`
- Можно выбрать в knowledge_profile/v2: **да**
- Готовность: `current_typed` — Materialization уже использует самостоятельный типизированный вход.
- KLC materialization: `code-declared-data-model`
- В базу знаний войдут: типы и сущности, объявленные в коде; поля и их типы; объявленные связи между типами; наследование; покрытие, доказательства и пробелы анализа кода
- Обязательные источники:
  - **Java type structure evidence** — `java-type-structure-evidence`; producer/analyzer: `java-type-structure-analyzer`; статус: `registered`

### Эффективное представление модели данных (`effective-data-model`)

Составное представление, связывающее независимо построенные модель из кода, физическую модель и доказанные логико-физические соответствия.

- Области: `repository, workspace`
- Можно выбрать в knowledge_profile/v2: **да**
- Готовность: `current_legacy` — Materialization работает через текущий runtime, но зависит от Task/Profile или старого формата входов.
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
  - **interaction-boundary-evidence** — `interaction-boundary-evidence`; producer/analyzer: `внешний/не зарегистрирован`; статус: `not_applicable`

### Контракты полей во взаимодействиях (`interaction-field-contracts`)

Связи полей и атрибутов на сопоставленных межсистемных взаимодействиях.

- Области: `workspace`
- Можно выбрать в knowledge_profile/v2: **да**
- Готовность: `current_partial` — Materialization работает, но целевая evidence-граница ещё неполна.
- KLC materialization: `interaction-field-contracts`
- В базу знаний войдут: поля входящих и исходящих сообщений; сопоставления полей; пути атрибутов через границы систем; пробелы и неоднозначности полевых контрактов
- Обязательные источники:
  - **Граф потоков значений репозитория** — `repository-value-flow`; producer/analyzer: `внешний/не зарегистрирован`; статус: `not_applicable`
  - **Сопоставленные взаимодействия репозиториев** — `repository-interaction-evidence`; producer/analyzer: `внешний/не зарегистрирован`; статус: `not_applicable`
- Рекомендуемые знания: `attribute-lineage`, `system-interactions`

### Острова взаимодействующих репозиториев (`interaction-islands`)

Связные группы репозиториев по подтверждённым и вероятным взаимодействиям.

- Области: `workspace`
- Можно выбрать в knowledge_profile/v2: **да**
- Готовность: `current_partial` — Materialization работает, но целевая evidence-граница ещё неполна.
- KLC materialization: `interaction-islands`
- В базу знаний войдут: строгие острова; расширенные острова; изолированные репозитории; состав и покрытие островов
- Обязательные источники:
  - **Сопоставленные взаимодействия репозиториев** — `repository-interaction-evidence`; producer/analyzer: `внешний/не зарегистрирован`; статус: `not_applicable`
- Рекомендуемые знания: `system-interactions`
- Дополнительные источники:
  - **Покрытие взаимодействий** — `interaction-coverage`; producer/analyzer: `внешний/не зарегистрирован`; статус: `not_applicable`

### Логико-физическое соответствие (`logical-physical-mapping`)

Доказательные соответствия сущностей и атрибутов из кода таблицам, колонкам, ключам и связям физической модели.

- Области: `repository, workspace`
- Можно выбрать в knowledge_profile/v2: **да**
- Готовность: `current_typed` — Materialization уже использует самостоятельный типизированный вход.
- KLC materialization: `logical-physical-mapping`
- В базу знаний войдут: сущность → таблица; атрибут → колонка; ключ модели → физический ключ; связь модели → физическая связь; конфликты и неразрешённые соответствия
- Обязательные источники:
  - **Java persistence mapping evidence** — `java-persistence-mapping-evidence`; producer/analyzer: `java-persistence-mapping-analyzer`; статус: `registered`
- Обязательные знания: `code-declared-data-model`, `physical-data-model`
- Обязательные модели KLC:
  - `code-declared-data-model` из `code-declared-data-model`
  - `physical-data-model` из `physical-model`

### Наблюдаемое использование хранилищ (`observed-storage-usage`)

Фактически наблюдаемые чтения, записи и обращения к объектам хранения из кода.

- Области: `repository, workspace`
- Можно выбрать в knowledge_profile/v2: **да**
- Готовность: `current_legacy` — Знание доступно через текущий legacy-путь; целевая KLC materialization по typed evidence ещё не реализована.
- KLC materialization: `observed-storage-usage`
- В базу знаний войдут: чтения из хранилищ; записи в хранилища; используемые таблицы, коллекции и поля; точки доступа в коде; неразрешённые цели хранения
- Обязательные источники:
  - **storage-usage-evidence** — `storage-usage-evidence`; producer/analyzer: `внешний/не зарегистрирован`; статус: `not_applicable`
- Рекомендуемые знания: `code-declared-data-model`, `physical-data-model`
- Дополнительные модели KLC:
  - `code-declared-data-model` из `code-declared-data-model`
  - `physical-data-model` из `physical-model`
- Дополнительные источники:
  - **model-evidence-gap** — `model-evidence-gap`; producer/analyzer: `внешний/не зарегистрирован`; статус: `not_applicable`

### Физическая модель данных (`physical-data-model`)

Таблицы, колонки, ключи, ограничения, связи и пробелы предоставленной физической модели.

- Области: `repository, workspace`
- Можно выбрать в knowledge_profile/v2: **да**
- Готовность: `current_typed` — Materialization уже использует самостоятельный типизированный вход.
- KLC materialization: `physical-model`
- В базу знаний войдут: таблицы; колонки; первичные и альтернативные ключи; внешние ключи и связи; ограничения; пробелы физической модели
- Обязательные источники:
  - **Предоставленная физическая модель** — `physical-model`; producer/analyzer: `внешний/не зарегистрирован`; статус: `not_applicable`

### Топология портфеля репозиториев (`portfolio-topology`)

Компактная топология и острова взаимодействий большого портфеля репозиториев.

- Области: `portfolio`
- Можно выбрать в knowledge_profile/v2: **нет**
- Готовность: `current_legacy` — Materialization работает через текущий runtime, но зависит от Task/Profile или старого формата входов.
- KLC materialization: `portfolio-topology`
- В базу знаний войдут: репозитории; границы взаимодействий; рёбра топологии; острова; покрытие
- Обязательные источники:
  - **repository-interface-catalog-evidence** — `repository-interface-catalog-evidence`; producer/analyzer: `внешний/не зарегистрирован`; статус: `not_applicable`
- Дополнительные источники:
  - **Метаданные репозитория и системы** — `repository-metadata`; producer/analyzer: `внешний/не зарегистрирован`; статус: `not_applicable`

### Справочные данные (`reference-data`)

Наблюдаемые значения, записи литералов, кандидаты справочников и контекст использования.

- Области: `repository, workspace`
- Можно выбрать в knowledge_profile/v2: **да**
- Готовность: `current_legacy` — Знание доступно через текущий legacy-путь; целевая KLC materialization по typed evidence ещё не реализована.
- KLC materialization: `reference-data`
- В базу знаний войдут: объявленные значения и перечисления; наблюдаемые литеральные записи; наборы значений; кандидаты справочников; контекст хранения и использования; неразрешённые альтернативы
- Обязательные источники:
  - **declared-value-evidence** — `declared-value-evidence`; producer/analyzer: `внешний/не зарегистрирован`; статус: `not_applicable`
  - **literal-write-evidence** — `literal-write-evidence`; producer/analyzer: `внешний/не зарегистрирован`; статус: `not_applicable`
- Дополнительные источники:
  - **java-persistence-evidence** — `java-persistence-evidence`; producer/analyzer: `внешний/не зарегистрирован`; статус: `not_applicable`
  - **value-flow-evidence** — `value-flow-evidence`; producer/analyzer: `внешний/не зарегистрирован`; статус: `not_applicable`
  - **interaction-boundary-evidence** — `interaction-boundary-evidence`; producer/analyzer: `внешний/не зарегистрирован`; статус: `not_applicable`
  - **configuration-evidence** — `configuration-evidence`; producer/analyzer: `внешний/не зарегистрирован`; статус: `not_applicable`

### SQL-инвентарь источников и назначений (`sql-source-inventory`)

SQL-операторы, таблицы, поля, роли использования, JOIN и доказательный source-to-target lineage.

- Области: `repository, workspace`
- Можно выбрать в knowledge_profile/v2: **да**
- Готовность: `current_typed` — Materialization уже использует самостоятельный типизированный вход.
- KLC materialization: `sql-analysis`
- В базу знаний войдут: SQL-операторы и области видимости; таблицы-источники и назначения; используемые поля; роли полей: projection, join, filter и другие; JOIN и условия связи; source-to-target lineage; неразрешённые ссылки и покрытие
- Обязательные источники:
  - **sql-analysis** — `sql-analysis`; producer/analyzer: `внешний/не зарегистрирован`; статус: `not_applicable`
- Дополнительные источники:
  - **Предоставленная физическая модель** — `physical-model`; producer/analyzer: `внешний/не зарегистрирован`; статус: `not_applicable`

### Описание системы (`system-description`)

Сценарии, внешние зависимости, хранилища, источники данных и границы доступа.

- Области: `repository, workspace`
- Можно выбрать в knowledge_profile/v2: **да**
- Готовность: `current_legacy` — Знание доступно через текущий legacy-путь; целевая KLC materialization по typed evidence ещё не реализована.
- KLC materialization: `system-description`
- В базу знаний войдут: системные сценарии; внешние зависимости; используемые хранилища; источники данных; границы доступа; покрытие и пробелы
- Обязательные источники:
  - **interaction-boundary-evidence** — `interaction-boundary-evidence`; producer/analyzer: `внешний/не зарегистрирован`; статус: `not_applicable`
  - **configuration-evidence** — `configuration-evidence`; producer/analyzer: `внешний/не зарегистрирован`; статус: `not_applicable`
  - **build-dependency-evidence** — `build-dependency-evidence`; producer/analyzer: `внешний/не зарегистрирован`; статус: `not_applicable`
  - **storage-access-evidence** — `storage-access-evidence`; producer/analyzer: `внешний/не зарегистрирован`; статус: `not_applicable`
- Дополнительные источники:
  - **value-flow-evidence** — `value-flow-evidence`; producer/analyzer: `внешний/не зарегистрирован`; статус: `not_applicable`
  - **physical-schema-evidence** — `physical-schema-evidence`; producer/analyzer: `внешний/не зарегистрирован`; статус: `not_applicable`

### Взаимодействия систем и репозиториев (`system-interactions`)

Подтверждённые и вероятные связи между входящими и исходящими интерфейсами.

- Области: `workspace`
- Можно выбрать в knowledge_profile/v2: **да**
- Готовность: `current_partial` — Materialization работает, но целевая evidence-граница ещё неполна.
- KLC materialization: `system-interactions`
- В базу знаний войдут: входящие и исходящие границы; протоколы и адреса; межрепозиторные взаимодействия; межсистемные взаимодействия; неоднозначные и неразрешённые сопоставления
- Обязательные источники:
  - **interaction-boundary-evidence** — `interaction-boundary-evidence`; producer/analyzer: `внешний/не зарегистрирован`; статус: `not_applicable`
- Дополнительные источники:
  - **configuration-evidence** — `configuration-evidence`; producer/analyzer: `внешний/не зарегистрирован`; статус: `not_applicable`
  - **execution-context-evidence** — `execution-context-evidence`; producer/analyzer: `внешний/не зарегистрирован`; статус: `not_applicable`

### Общий SQL-каталог workspace (`workspace-sql-source-inventory`)

Агрегированный каталог SQL-витрин, источников и назначений нескольких репозиториев.

- Области: `workspace`
- Можно выбрать в knowledge_profile/v2: **да**
- Готовность: `current_legacy` — Знание доступно через текущий legacy-путь; целевая KLC materialization по typed evidence ещё не реализована.
- KLC materialization: `workspace-sql-mart-catalog`
- В базу знаний войдут: SQL-витрины workspace; общий инвентарь таблиц и полей; источники и назначения по репозиториям; межрепозиторные соответствия; покрытие и пробелы
- Обязательные источники:
  - **sql-analysis** — `sql-analysis`; producer/analyzer: `внешний/не зарегистрирован`; статус: `not_applicable`
- Рекомендуемые знания: `sql-source-inventory`
- Дополнительные источники:
  - **Предоставленная физическая модель** — `physical-model`; producer/analyzer: `внешний/не зарегистрирован`; статус: `not_applicable`
  - **Метаданные репозитория и системы** — `repository-metadata`; producer/analyzer: `внешний/не зарегистрирован`; статус: `not_applicable`

## Внутренние materializations

- `common-data-model` — Текущий legacy umbrella; заменяется отдельными code-declared, physical, mapping, observed-usage и effective знаниями.
- `suite-evidence-registry` — Технический реестр выполнения и артефактов, а не самостоятельное бизнес-знание.

## Следующий шаг

`generic_knowledge_architecture_audit/v1_for_code-declared-data-model`
