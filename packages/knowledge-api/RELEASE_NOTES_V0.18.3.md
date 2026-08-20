# knowledge-api 0.18.3

Adds a deterministic read-only projection for `cross-artifact-data-model-mapping/v3`.

- New `GET /api/knowledge/v1/systems/{system_id}/data-model/lineage`.
- Publishes only KLC-materialized logical-field → physical-column lineage; API performs no new inference.
- Includes observed SQL source/file/column when available, workflow target, PDM column, transform expression, knowledge class, path evidence and provenance.
- Supports deterministic pagination and exact filters plus search.
- Adds aggregate counts for paths, logical fields, target tables/columns and SQL files.
