# Data-model relationship contract — knowledge-api 0.8.0

The table-detail endpoint returns a compact relationship projection intended for downstream JOIN construction.

Compact relationship fields:

- `relationship_id`;
- `kind`;
- `source_field` and `cardinality`;
- target object identity and aliases;
- `join.method`;
- source/target fields and expressions when observed;
- `requires_encoding_interpretation`;
- `physical_join_confirmed`;
- optional join semantics required for collections or parent-key relationships.

It intentionally excludes logical-identity classification, storage-key evidence, AST trees, parameter bindings, converter operations and provenance.

Full technical evidence is available from:

```http
GET /api/knowledge/v1/systems/{system_id}/data-model/tables/{table_id}/relationships/{relationship_id}
```

For encoded references such as `Individual.birthDate`, the compact contract preserves the target alias and target storage-key field while keeping `physical_join_confirmed=false` and `requires_encoding_interpretation=true`.


## Artifact Store GC

`POST /api/knowledge/v1/artifact-store/gc` is an operational AISL persistence-lifecycle endpoint. `plan` is non-destructive. `sweep` requires `confirm_delete_unreferenced=true`; `grace_period_seconds` is supplied by the operator and is not a semantic retention policy. Reachability is derived only from all retained committed revisions in the canonical Catalog. No refcount registry is maintained.
