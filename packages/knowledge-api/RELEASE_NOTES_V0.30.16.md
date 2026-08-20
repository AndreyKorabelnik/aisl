# Knowledge API 0.30.16 release notes

- Added `reference-data-guidance/v1` compact facts-only projection.
- Added GET `/api/knowledge/v1/systems/{system_id}/reference-data/guidance`.
- Supports compact global discovery and optional token-scoped exact technical context.
- Preserves KLC totals/provenance while bounding LLM-facing details.
- Explicitly performs no Reference Data semantic/ownership derivation.
- Existing detailed Reference Data query surface is unchanged.
- OpenAPI/public route contracts updated.
