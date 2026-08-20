# knowledge-layer-core 0.46.0

## Confirmed HTTP transport edges

- Added direct cross-repository HTTP transport edges to the canonical value-flow graph.
- Request flow is source outbound wire -> target inbound wire.
- Response flow is target inbound response wire -> source outbound response wire.
- Transport requires an existing matched, confirmed `system_boundary_interaction`.
- Exact unique normalized wire paths are required on both interface contracts.
- Transport does not depend on ingress or `system_interaction_execution_context`.
- Probable, ambiguous and unresolved boundary matches do not create transport edges.
- Replaced the single edge `repo_id` with canonical `source_repo_id` and `target_repo_id`; local edges set both to the same repository.
- No parallel transport table, compatibility view or dual-write was introduced.

## Schema

- package: `knowledge-layer-core 0.46.0`
- suite schema: `knowledge_layer_suite_scope/v14`
- direct graph schema: `repository_value_flow/v4`
