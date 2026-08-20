# analysis-ui 2.0.0a8 — unified system domain

Iteration 8 replaces the separately mounted data-model application with native, versioned system resources inside the canonical generic API.

## Unified publication model

A published revision stores:

```text
system_id
revision_id
source_job_id
knowledge_layer_artifact_id
report_artifact_id (optional)
```

Full-pipeline jobs publish automatically in the final `publication` stage. `target.system_id` controls the stable public ID; otherwise repository/workspace ID is used. Publication may be disabled with `parameters.publish_system=false`.

## Canonical endpoints

```text
POST /api/v1/systems
GET  /api/v1/systems
GET  /api/v1/systems/{system_id}
GET  /api/v1/systems/{system_id}/revisions
GET  /api/v1/systems/{system_id}/data-model/tables
GET  /api/v1/systems/{system_id}/data-model/tables/{table_id}
GET  /api/v1/systems/{system_id}/reports
GET  /api/v1/systems/{system_id}/reports/latest/content
GET  /api/v1/systems/{system_id}/reports/{revision_id}/content
```

Old data-model URLs and schema names are intentionally not retained.

## Preserved result quality

The reusable query adapter was moved into `analysis-ui` and still uses the public `knowledge-layer-core` typed facade. It preserves:

- physical SQL/DDL/jOOQ tables;
- logical model objects;
- fields and descriptions;
- keys;
- declared and observed relationships;
- target fields and JOIN recipes;
- explicit revision selection.

## Simplification

Removed:

- runtime dependency on `knowledge-api`/`data-model-api`;
- second FastAPI application;
- route mounting and route-set validation;
- external systems registry and report path configuration;
- separate data-model capability/version probing;
- second frontend data-model client.

Added:

- `systems` and `system_revisions` SQLite metadata;
- `SystemCatalogService`;
- cached `DataModelQueryAdapter`;
- one OpenAPI document and error model;
- provenance and deletion protection for published jobs;
- retry from the `publication` stage.

## Real artifact validation

The moved adapter was tested with the 18 MB real smoke Knowledge Layer produced by runner/core/KLC. It returned two physical tables; table detail included three fields, one key and one relationship. The same artifact and report were then published and read through the real HTTP routes.
