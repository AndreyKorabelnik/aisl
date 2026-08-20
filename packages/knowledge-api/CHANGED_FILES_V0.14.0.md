# knowledge-api 0.14.0

Iteration 95: expose deterministic SQL target resolution and attribute insertion context.

## Changes

- Added `GET /systems/{system_id}/sql/target-candidates`.
- Added `POST /systems/{system_id}/sql/attribute-insertion-context`.
- Added public request/response models for both read-only contracts.
- Added Knowledge Layer adapter methods for KLC 0.52.9 queries.
- Normalized nested `*_json` values before returning them through the public API.
- Updated the canonical OpenAPI document.
- Raised the minimum KLC dependency to 0.52.9.

## Unchanged

- No SQL analysis, lineage, materialization or source repository code was modified.
- The API does not edit SQL, choose a target silently, or invoke an LLM.
