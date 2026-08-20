# Предварительный состав базы знаний: Generic Core evidence runtime smoke

- Профиль: `generic-core-evidence-smoke`
- Область: `repository:smoke-repository`
- Статус плана: `current_typed`
- Fingerprint: `f0a140d3df2d5fa162ce81e6e831ff69becba11f7a76df8f47a4aa2e04c8a121`
- Фактическое наличие исходников: **ещё не проверялось**

## Что войдёт в базу знаний

### Модель данных, объявленная в коде

Типы, поля, объявленные связи и наследование, непосредственно наблюдаемые в исходном коде.

Добавлено в план: `user_requested`

Будут построены: типы и сущности, объявленные в коде; поля и их типы; объявленные связи между типами; наследование; покрытие, доказательства и пробелы анализа кода

Источники:
- **Java type structure evidence** (обязательный) — `java-type-structure-evidence`; фактическая доступность: `not_assessed`

## Технический план

### KLC materializations

- `code-declared-data-model` для `code-declared-data-model` — `current_typed`

### Зависимости между моделями KLC


### Foundation

`java_syntax_index`, `source_file_inventory`

## Диагностика

- `info` `source_availability_not_assessed` — This read-only resolution uses contracts only and does not inspect the selected repository/workspace.
