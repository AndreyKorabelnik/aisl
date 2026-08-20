# knowledge-layer-core 0.37.1

## Boundary operation cardinality

- Added explicit `execution_context_count` to repository-level `system_interaction` rows.
- Confirmed that multiple local ingress paths share one canonical boundary interaction.
- Repository `operation_count` now remains the count of unique outbound-to-inbound boundary operations, not local execution scenarios.
- Added regression coverage for two REST ingress triggers reaching one outbound boundary.
