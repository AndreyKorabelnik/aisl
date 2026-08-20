# knowledge-layer-core 0.31.0

## Strict request attribute lineage

- Imports production field occurrences and field-flow edges from completed `flow-lineage` tasks.
- Materializes deterministic source-ingress request field → outbound request field paths for each matched operation interaction.
- Every source attribute that participates in a target-field calculation is preserved as a separate lineage edge.
- Does not reconcile the outbound wire contract with the target repository yet and does not use fuzzy field matching.
- Adds compact query and evidence access under capability `workspace.system-interaction-attribute-lineage`.
