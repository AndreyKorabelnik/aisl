# knowledge-layer-core 0.32.2

## Iteration 31.3 — exact collection-member outbound contracts

- Ingests compact signature-aware `method_references.json` records.
- Reconstructs nested outbound collection-member wire paths only from exact method-reference binding, observed collection-result assignment, nested builder structure and an exact target request contract.
- Keeps terminal member paths and suppresses container-only paths when a more specific child path is proven.
- Publishes `exact_collection_member_builder_path` contracts with full deterministic provenance.
- Does not add attribute lineage; lineage composition remains a separate stage.
- Uses no fuzzy, semantic, pluralization or leaf-name matching.

Validated on the four-system workspace:

- systems: 4;
- system interactions: 3;
- operation interactions: 9;
- request field contracts: 228 → 231;
- request attribute lineage: 54, unchanged;
- new contracts: `phone.flags.flagType.code`, `phone.flags.updateDateTime`, `phone.flags.endDate`.
