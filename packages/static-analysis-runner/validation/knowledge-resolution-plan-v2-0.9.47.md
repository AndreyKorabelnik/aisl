# Предварительный состав базы знаний: Модель данных из кода

- Профиль: `code-declared-model`
- Область: `repository:repo-a`
- Статус плана: `current_typed`
- Fingerprint: `0efea68bfc9abd9ab7ac07c74fa0c905f125d70d81990557b53f1af7e3ce70d8`
- Фактическое наличие исходников: **ещё не проверялось**

## Что войдёт в базу знаний

### Модель данных, объявленная в коде

Типы, поля, объявленные связи и наследование, непосредственно наблюдаемые в исходном коде.

Добавлено в план: `user_requested`

Будут построены: типы и сущности, объявленные в коде; поля и их типы; объявленные связи между типами; наследование; покрытие, доказательства и пробелы анализа кода

Источники:
- **Объявления типов и полей в исходном коде** (обязательный) — `java-type-structure-evidence`; фактическая доступность: `not_assessed`

## Технический план

### KLC materializations

- `code-declared-data-model` для `code-declared-data-model` — `current_typed`

### Зависимости между моделями KLC


### Источники Core (расширенная диагностика)

- `java_source_observation_build` → Объявления типов и полей в исходном коде; знания: `code-declared-data-model`
- `java_structural_scan` → Объявления типов и полей в исходном коде; знания: `code-declared-data-model`

### Foundation

`java-structure-index`, `repository-file-index`, `symbol-and-type-index`

## Диагностика

- `info` `source_availability_not_assessed` — This read-only resolution uses contracts only and does not inspect the selected repository/workspace.
