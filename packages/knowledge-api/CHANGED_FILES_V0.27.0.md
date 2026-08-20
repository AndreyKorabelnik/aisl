# knowledge-api 0.27.0

## Purpose
Provide a minimal external-LLM read surface for already-prepared relation-materialization and SQL query/scope context, and align data-model lineage with the current cross-artifact v6 schema.

## Changes
- Added `GET /api/knowledge/v1/systems/{system_id}/sql/relation-materializations`.
- Added `GET /api/knowledge/v1/systems/{system_id}/sql/query-context`.
- Both endpoints are thin read-only wrappers over existing Prepared Knowledge/KLC queries.
- Fixed `/data-model/lineage` to read the actual `cross-artifact-data-model-mapping/v6` columns; removed reads of obsolete/nonexistent `source_resolution_status` and `source_unresolved_placeholders` fields.
- Updated API models, route contract, OpenAPI snapshot, and route allowlist.

## Non-changes
- No Producer fallback.
- No new Knowledge Layer semantics.
- No Core/Runner/Reporting/Assistant/UI dependency.
