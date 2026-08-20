# Iteration 19 — диагностика typed-reference и storage-key evidence

## Статус

Итерация завершена как диагностический checkpoint. Публичный JSON отношений, DuckDB-схема и materialization не изменялись.

Добавлен универсальный read-only diagnostic в `knowledge-layer-core 0.24.1`, который объясняет, какие evidence присутствуют и чего не хватает для физического JOIN.

## Принцип универсальности

Диагностика не содержит условий по UCP, пакетам, классам, именам полей или alias-строкам. Она использует только:

- `model_relationship_observation`;
- logical model keys и их members;
- AST-derived `key(...)`, `alias(...)` и reference operations;
- call-result bindings;
- return/reference derivations;
- storage-key lineage;
- polymorphic target observations;
- формальные semantic observations encoding, если они существуют.

UCP используется только как реальный regression case.

## Подтверждённый путь evidence

```text
Java AST/source observations
→ code-analyzer-core TSA interpreter
→ repository evidence
→ knowledge-layer-core materialization
→ DataModelQueryService join_guidance
→ knowledge-api
```

## Первопричина 1 — scope-insensitive local result binding в core

Текущий `code-analyzer-core` при обработке:

```java
String refKey = convertChild(...);
parent.referenceField("child", refKey);
```

сначала ищет result binding по parent-call. Если reference принимает локальную переменную, fallback выполняется по ключу:

```text
(owner_operation, variable_name)
```

После этого derivation создаётся только при ровно одном кандидате.

Это видно в `code_analyzer_core/tsa_interpreter.py`, строки 495–507 текущего baseline.

Для двух отдельных lexical blocks с одинаковым именем переменной generic fixture даёт:

- 2 reference operations;
- 2 call-result bindings с `target_variable=refKey`;
- 0 `tsa_reference_value_derivation_observation`.

Фреймворк не угадывает, но теряет точный flow. Требуемое исправление — учитывать lexical scope и source position/dominating assignment, а не имена бизнес-классов или полей.

На полном UCP для `Individual.birthDate` обнаружены два converter paths:

- JSON converter: 27 result-binding candidates для повторно используемого локального имени;
- POJO converter: 22 candidates;
- 0 точных reference-value derivations для `birthDate`.

## Первопричина 2 — storage record key не является first-class сущностью KLC

KLC уже сохраняет наблюдения:

- `alias(...)`;
- `key(...)`;
- key expressions;
- relationship target expressions;
- storage-key lineages для части коллекций.

Но exact correspondence строится только через `model_object_key_member`. Эта таблица описывает logical identity, извлечённую, например, из model annotations.

Для `BirthDate` logical members:

```text
id
version
```

Наблюдаемое storage-key expression:

```text
parentKey + '.' + fieldName
```

Физическое поле `key` не представлено отдельным canonical storage-record-key контрактом. Поэтому выражение builder `key(...)` нельзя корректно опубликовать как physical target field, не смешивая его с `id/version`.

Это видно в `knowledge_layer_core/workspace_data_model.py`:

- строки 977–986 загружают только `model_object_key_member`;
- `_canonical_key_expression_node()` принимает только поля из этого списка;
- storage key assignment остаётся expression evidence, а не physical key model.

## Первопричина 3 — нет доказанной семантики reference encoding

Наличие раздельных вызовов:

```java
builder.key(key);
builder.alias(alias);
parent.referenceField(field, returnedKey);
```

не доказывает само по себе, что внешняя библиотека сериализует значение как:

```text
normalize(alias) + ':' + key
```

В двух переданных приложениях нет реализации внешнего builder API, которая подтверждала бы:

- separator;
- alias normalization;
- формат source value;
- поведение scalar/collection/polymorphic references.

Реальные значения таблиц являются сильным validation evidence для UCP, но не должны превращаться в универсальное правило core без formal API semantics или исходников библиотеки.

Поэтому новый diagnostic намеренно возвращает:

```json
{
  "reference_encoding": {"status": "unresolved"},
  "physical_join": {"confirmed": false}
}
```

и не придумывает `type_prefixed_key`.

## Сравнение реальных типов отношений

| Связь | Семантика | Flow | Logical correspondence | Storage key | Encoding |
|---|---|---|---|---|---|
| `birthDate` | scalar reference | ambiguous | отсутствует | наблюдается, не first-class | unresolved |
| `birthPlace` | scalar reference | ambiguous | отсутствует | наблюдается, не first-class | unresolved |
| `birthCountry` | dictionary/reference | наблюдается | подтверждено по `code` | наблюдается, не first-class | unresolved |
| `addresses` | collection | collection lineage частично наблюдается | отсутствует | наблюдается, не first-class | unresolved |
| `identifications` | polymorphic collection | collection-specific | не применимо к abstract target | 8 concrete targets и их key calls наблюдаются | unresolved |

Это подтверждает, что relation semantics и storage encoding должны моделироваться независимо.

## Текущий безопасный baseline API

Публичный query surface сейчас не утверждает физический JOIN:

- `birthDate` и `birthPlace`: `method=derived_storage_key`, `physical_join_confirmed=false`;
- `birthCountry`: exact expression correspondence с logical `code`, но также `physical_join_confirmed=false`;
- collections/polymorphic relations: key expressions опубликованы, physical JOIN не подтверждён.

То есть старый ошибочный `equals` уже не является текущим baseline. Следующая работа должна завершить evidence chain, а не подменить безопасный unresolved результат новым предположением.

## Добавленный diagnostic API

```bash
python -m knowledge_layer_core.relationship_diagnostics \
  --database path/to/knowledge-layer.duckdb \
  --relationship-id <relationship-id> \
  --output relationship-diagnostic.json
```

Diagnostic публикует:

- logical identity observations;
- target alias assignments;
- target storage-key assignments;
- local result-binding candidates;
- reference-value derivations;
- storage lineages;
- polymorphic targets;
- correspondence status;
- encoding status;
- root causes;
- safety flags, подтверждающие отсутствие inference.

## Следующий этап — Iteration 20

1. Сделать result-binding resolution lexical-scope/source-position aware в `code-analyzer-core`.
2. Добавить generic fixture с повторным именем переменной в разных блоках и требовать две точные derivations.
3. Сохранить exact call/return provenance и не выбирать неоднозначный candidate.
4. Ввести formal facts-only semantic observation contract для внешних builder APIs.
5. Не выводить encoding из method names; semantic contract должен быть явно подключён и иметь provenance.
6. После быстрого core regression пересобрать UCP repository evidence и проверить `birthDate`, `birthPlace`, dictionary и collection examples.
7. Только после этого переходить к first-class storage-key schema в KLC.
