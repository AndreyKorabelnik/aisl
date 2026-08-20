Для UCP replica storage интерпретируй только scalar storage reference с `join.method=storage_reference_requires_encoding` так:

- type component берётся из `target.aliases`;
- physical type prefix получается заменой `.` на `_`;
- separator между type prefix и storage key — `:`;
- key component берётся из `target.storage_key.fields`;
- SQL predicate: `<source_alias>.<source.field> = CONCAT('<normalized_target_alias>:', <target_alias>.<storage_key_field>)`.

Не используй `target.logical_identity` как physical key. Для `cardinality=many` и полиморфных коллекций не придумывай container/membership SQL: покажи aliases и storage-key expressions и зафиксируй gap, пока формат коллекции не задан отдельно.
