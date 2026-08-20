# knowledge-api 0.20.0 — code-declared data-model read surface

Adds a thin revision-bound HTTP read surface over the already prepared `code-declared-data-model/v1` artifact:

- `GET /api/knowledge/v1/systems/{system_id}/data-model/declared-objects`
- `GET /api/knowledge/v1/systems/{system_id}/data-model/declared-objects/{object_id}`

The API delegates search/detail semantics to `knowledge-layer-core` and keeps declared-code facts explicitly separate from `effective-data-model`, storage mappings, physical JOIN semantics and final SQL. No Core/Runner/materialization rerun is required for an existing revision that already contains the typed artifact.
