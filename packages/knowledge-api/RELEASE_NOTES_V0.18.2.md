# knowledge-api 0.18.2

Adds canonical attribute-path resolution over typed value-flow knowledge.

- New `POST /api/knowledge/v1/systems/{system_id}/attribute-paths/resolve` endpoint.
- Deterministically prefers `cross-repository-value-flow` when the revision publishes it; otherwise uses repository-local value flow.
- Response explicitly reports the selected source materialization and whether cross-repository enrichment is active.
- Exposes `strict`, `working`, and `exploratory` deterministic knowledge views produced by KLC.
