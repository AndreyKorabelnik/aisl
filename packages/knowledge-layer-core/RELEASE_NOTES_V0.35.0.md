# knowledge-layer-core 0.35.0

## Iteration 31.4 R3 — whole-object interaction lineage

- Adds canonical `system_interaction_object_lineage` for exact whole-object passthroughs.
- Keeps object identity separate from field lineage; no synthetic `* → *` field mappings are created.
- Requires one exact response-wrapper inner type, one exact object path, and only identity-preserving observed edge kinds.
- Rejects type mismatches, transformed paths and ambiguous response result targets.
- Adds deterministic query and evidence-tool access.
- Preserves all existing 58 request and 36 response field-lineage rows.

Validation: 4 systems / 3 system edges / 9 operation edges / 231 request field contracts / 94 field lineage / 1 object lineage. Manual response coverage: 21/21 when field and object lineage are considered together.
