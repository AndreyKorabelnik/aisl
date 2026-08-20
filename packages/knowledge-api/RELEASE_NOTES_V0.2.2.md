# knowledge-api 0.2.2

Fixes logical object detail for repository and suite Knowledge Layers that do not expose the workspace-only `model_relationship_candidates` query.

- `GET /api/v1/systems/{system_id}/tables/{table_id}` no longer returns HTTP 500 for UCP logical objects.
- Fields, keys and resolved relationships continue to come from the stable `DataModelQueryService` facade.
- `relationship_candidate_count` safely defaults to `0` when candidate diagnostics are unavailable; the existing HTTP serializer omits this zero default.
- The five-path public HTTP contract is unchanged.
