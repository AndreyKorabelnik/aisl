# knowledge-layer-core 0.32.3

## Iteration 31.3 — exact collection-member attribute lineage

- Composes collection-member input fields through an exact signature-resolved method reference and observed helper field-flow.
- Uses confirmed `exact_collection_member_builder_path` field contracts to bind reconstructed outbound fields to the target system contract.
- Treats an ingress field as participating in a transformation when its exact member path is a prefix of the observed helper-local field path.
- Preserves guarded value dependencies separately from control dependencies.
- Publishes `lineage_kind=control_dependency` when an input controls whether a target field is assigned, rather than pretending that the control value is copied into that field.
- Rejects ambiguous source prefixes, method-reference bindings, builder targets and field-flow paths.
- Uses no fuzzy, semantic, pluralization or approximate leaf-name matching.

Validated on the four-system workspace:

- systems: 4;
- system interactions: 3;
- operation interactions: 9;
- request field contracts: 231;
- request attribute lineage: 54 → 58;
- removed existing lineage: 0;
- added collection-member lineage: exactly 4.
