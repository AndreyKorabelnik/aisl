# Canonical Knowledge API contract

Base prefix: `/api/knowledge/v1`  
Contract envelope schema: `knowledge_api/v1`

## Knowledge execution publication (0.30.11)

The only publication input is a completed `knowledge_execution_result/v2`. A revision contains the execution summary, typed knowledge artifacts, materialization capabilities and an optional report. The API does not accept a caller-selected combined DuckDB.

Incremental same-system publication MAY provide an exact `base_revision_id`. The publisher then creates one new immutable copy-on-write snapshot: unchanged base products are retained by exact artifact identity and newly produced products replace their `source_materialization_id` owner slots. Same-system `external_knowledge_artifacts[]` require that explicit base; active/latest is never guessed. Cross-system dependencies remain provenance only. Consumers still read one pinned revision.

```http
POST /api/knowledge/v1/systems/{system_id}/revisions
GET  /api/knowledge/v1/systems/{system_id}/knowledge-artifacts
GET  /api/knowledge/v1/systems/{system_id}/knowledge-artifacts/{artifact_id}
GET  /api/knowledge/v1/systems/{system_id}/capabilities
```

Data-model routes require `effective-data-model/v1`; physical routes require `physical-data-model`; SQL routes require a `common.sql*` capability. Missing models are explicit errors.

## System administration (0.7.0)

```http
PATCH  /api/knowledge/v1/systems/{system_id}
DELETE /api/knowledge/v1/systems/{system_id}
POST   /api/knowledge/v1/systems/{system_id}/revisions/{revision_id}/activate
```

PATCH uses top-level metadata merge semantics. A metadata value of `null` deletes that key. `system_id` is immutable.

DELETE is a permanent cascade over the system and all immutable revisions. Operational clients should require explicit user confirmation before issuing it.


## Relationship detail (0.8.0)

```http
GET /api/knowledge/v1/systems/{system_id}/data-model/tables/{table_id}/relationships/{relationship_id}
```


## SQL relation inventory (0.10.0)

```http
GET /api/knowledge/v1/systems/{system_id}/sql/relations
```

Returns external SQL relations and fields actually used from them, with usage roles,
coverage and evidence. SQL-only revisions are supported.


### SQL relation view

The `view` query parameter accepts:

- `business_sources` (default): user-facing external sources only;
- `technical`: hidden technical/intermediate physical relations;
- `all`: all physical and template relations.

Technical naming is never the only classification basis. The response exposes semantic role, classification status, reasons and classification coverage.


## SQL target resolution (0.14.0)

```http
GET  /api/knowledge/v1/systems/{system_id}/sql/target-candidates
POST /api/knowledge/v1/systems/{system_id}/sql/attribute-insertion-context
```

Both endpoints are revision-aware read-only projections over KLC facts. The first returns
ranked write targets with reasons and alternatives. The second returns ranked SQL scopes
for introducing a source attribute plus the target workflow context and diagnostics.
Neither endpoint invokes an LLM or changes repository content.


## Physical model (0.15.0)

```http
GET /api/knowledge/v1/systems/{system_id}/physical-model
GET /api/knowledge/v1/systems/{system_id}/physical-model/tables
GET /api/knowledge/v1/systems/{system_id}/physical-model/tables/{table_id}
GET /api/knowledge/v1/systems/{system_id}/physical-model/columns
GET /api/knowledge/v1/systems/{system_id}/physical-model/keys
GET /api/knowledge/v1/systems/{system_id}/physical-model/relationships
GET /api/knowledge/v1/systems/{system_id}/physical-model/gaps
```

These endpoints expose deterministic typed PDM facts. Table search covers physical/logical table names and codes plus column names/codes. PDM facts never determine SQL `read`/`write` roles.
