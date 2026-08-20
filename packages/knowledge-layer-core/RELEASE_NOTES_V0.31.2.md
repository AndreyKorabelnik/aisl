# knowledge-layer-core 0.31.2

## Iteration 31 — field-lineage path quality

- Keeps only terminal request-contract fields when a contract exposes both an object
  container and its concrete children. This prevents coarse duplicates such as
  `profile.email -> electronicAddress` beside exact child mappings.
- Rejects `object_field_contribution_to_built_object` as proof of field-to-field
  interaction lineage. That evidence proves whole-object participation, not that every
  source field transformed into every field of the built object.
- Rejects a collection/container source when the outbound field is only an unverified
  observed object field without a confirmed wire contract. Scalar paths remain eligible.
- Preserves exact collection transformation paths such as
  `scopes -> stream/map/collect -> String.join -> scope`.
- Uses only structural Java types, exact contract paths and observed edge semantics;
  no repository-, package-, class-, method- or field-specific allowlists were added.

Validated on the four-system interaction workspace:

- system interactions: 3;
- operation interactions: 9;
- request attribute lineage: 48 -> 49;
- manual-baseline matches: 49/49;
- extra rows: 0;
- the only new semantic mapping is `scopes -> scope`.
