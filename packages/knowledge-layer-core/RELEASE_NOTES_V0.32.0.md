# knowledge-layer-core 0.32.0

## Iteration 31.3 — exact cross-repository request field contracts

- Adds canonical `system_interaction_field_contract` materialization.
- Matches only unique request wire paths across an already confirmed operation interaction.
- Keeps outbound and inbound payload type, declared field type, source schema and evidence provenance.
- Separates protocol contract continuity from attribute transformation lineage.
- Adds query and evidence-tool access through `system_interaction_field_contracts`.
- Adds capability `workspace.system-interaction-field-contracts`.
- Rejects normalized-path ambiguity instead of selecting one candidate.
- Uses no fuzzy, semantic, pluralization or leaf-name matching.

Validated on the four-system workspace:

- systems: 4;
- system interactions: 3;
- operation interactions: 9;
- exact request field contracts: 228;
- existing request attribute lineage: 51, unchanged.
