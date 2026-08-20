# knowledge-layer-core 0.30.0

## Workspace system interaction graph

- Materializes deterministic cross-repository HTTP system interactions from existing suite evidence.
- Adds canonical `system_interaction` and `system_interaction_operation` tables.
- Uses exact/normalized endpoint paths, HTTP method, request contract overlap and observed method-call reachability.
- Deduplicates duplicate target-interface projections for the same physical endpoint.
- Preserves unmatched and ambiguous outbound interfaces in `system_interaction_match_diagnostic` instead of inventing edges.
- Adds compact query methods for system edges, operation edges, diagnostics and the complete workspace graph.
- Ingests `method_calls.json` as a suite query artifact.

No static-analysis extractor was changed.
