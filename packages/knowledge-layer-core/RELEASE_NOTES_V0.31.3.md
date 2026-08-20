# knowledge-layer-core 0.31.3

## Iteration 31 — direct mapper derivation composition

- Composes a confirmed `attribute_derivation` when it is located directly in the mapper
  operation called by the outbound operation.
- Requires exact overload resolution (`exact_argument_types`) and one exact same-object
  request DTO parameter binding.
- Requires an unambiguous builder target and an exact outbound request-contract field.
- Keeps ambiguous calls, multi-source derivations and missing contract fields unresolved.
- Adds no fuzzy field-name matching and no repository-, class-, method- or field-specific rules.

Validated on the four-system interaction workspace:

- system interactions: 3;
- operation interactions: 9;
- request attribute lineage: 49 -> 51;
- new rows: exactly two `sberProfileId -> sberProfileId` mappings for update-light and LK update;
- removed previous rows: 0;
- extra rows: 0.
