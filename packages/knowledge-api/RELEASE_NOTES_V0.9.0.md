# knowledge-api 0.9.0

## SQL relation and field inventory

The canonical API now supports SQL-only Knowledge Layer revisions produced by
`knowledge-layer-core >=0.50.0`.

New endpoint:

```http
GET /api/knowledge/v1/systems/{system_id}/sql/relations
```

It returns logical external SQL relations together with the fields actually used from
each relation, usage roles, resolution statuses, analysis coverage and repository-relative
evidence.

By default only `physical` and `physical_template` relations are returned. CTE and derived
relations remain available only when requested explicitly through `relation_kind`.

Supported filters:

- `revision_id`;
- `repo_id`;
- `relation_kind`;
- `usage_role`;
- `search`;
- `include_fields`;
- `offset` and `limit`.

## Publication and compatibility

- SQL-only DuckDB revisions no longer require data-model tables to be publishable.
- Publication validation accepts a revision when it contains either queryable data-model
  facts or queryable SQL relation facts.
- Data-model endpoints return `409 data_model_unavailable` for SQL-only revisions instead
  of attempting invalid data-model queries.
- The KLC dependency is now `knowledge-layer-core>=0.50.0,<1.0.0`.

## Scope

This release exposes relation/field inventory only. Field explanation, recursive lineage,
JOIN graph and field-addition planning remain separate follow-up iterations.
