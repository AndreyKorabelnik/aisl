# knowledge-api 0.11.0

- Added `GET /systems/{system_id}/sql/column-usages/{usage_id}`.
- The response exposes deterministic scope context for ambiguous or unresolved SQL fields.
- Requires `knowledge-layer-core>=0.51.3`.
