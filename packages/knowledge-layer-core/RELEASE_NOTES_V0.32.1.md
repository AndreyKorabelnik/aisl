# knowledge-layer-core 0.32.1

## Iteration 31.3 — nested helper request lineage

- Composes a three-level observed call corridor: outbound operation → mapper → container helper → nested helper.
- Requires exact method-call signatures and exact source contract type bindings.
- Requires an observed local field-flow path into the nested builder field.
- Requires AST-span evidence connecting the builder field to the returned nested object.
- Requires the nested return to flow into the outer container builder.
- Resolves the final outbound path only through a unique exact cross-repository wire-field contract.
- Uses no fuzzy, semantic, pluralization or leaf-name matching.

Validated on the four-system workspace:

- systems: 4;
- system interactions: 3;
- operation interactions: 9;
- exact request field contracts: 228;
- request attribute lineage: 51 → 54;
- added nested flag transformations: 3;
- removed existing lineage: 0;
- unexpected lineage: 0.
