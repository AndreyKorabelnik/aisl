# knowledge-layer-core 0.59.3

Restores cross-repository HTTP transport edges in the typed value-flow pipeline.

New typed materialization: `cross-repository-value-flow`.
Inputs: `repository-value-flow`, `system-interactions`, `interaction-field-contracts`.
It reuses the existing `materialize_repository_value_flow` transport-enrichment logic and publishes the enriched value-flow graph without Task/Suite, topology, fallback, or dual-write.
