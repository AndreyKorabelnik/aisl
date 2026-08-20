# knowledge-api 0.30.12

Adds a thin consumer-oriented read projection for existing KLC attribute-extension knowledge.

- New `GET /api/knowledge/v1/systems/{system_id}/data-model/attribute-extension-guidance` endpoint.
- The endpoint reuses the canonical attribute-extension context read and only selects/bounds already-published fields; it does not classify relationships, infer JOINs, choose business meaning or generate SQL.
- KLC-owned `basis.usefulness` is promoted verbatim for actionability, while technical confidence, ambiguity, residual checks, diagnostics and gaps remain explicit.
- Exact-vs-analog SQL JOIN examples, storage-reference observations, key/reference expressions and compact SQL anchors are visible early in the payload.
- Bounded collections report explicit truncation metadata when truncation occurs, and the canonical full-detail endpoint remains available.
- Depends on `knowledge-integration==0.1.11`.
