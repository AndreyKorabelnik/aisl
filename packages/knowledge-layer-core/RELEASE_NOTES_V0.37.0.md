# knowledge-layer-core 0.37.0

## Canonical boundary interaction model

- Replaced ingress-dependent `system_interaction_operation` with `system_boundary_interaction`.
- Boundary interactions are created immediately after a unique outbound-to-inbound match, even when no source ingress path is observed.
- Added independent `system_interaction_execution_context` records for optional trigger-to-outbound call paths.
- Boundary IDs no longer include source ingress identity; multiple local execution contexts reference one boundary interaction.
- Added explicit `match_status`, `confidence`, and `local_execution_status` fields.
- Updated field-contract and lineage materializers to consume the new canonical model.
- Removed legacy operation query/tool surface and added boundary-interaction and execution-context queries.
- Added regression coverage for a matched outbound call without any source ingress.

No backward-compatible legacy schema or adapters are included.
