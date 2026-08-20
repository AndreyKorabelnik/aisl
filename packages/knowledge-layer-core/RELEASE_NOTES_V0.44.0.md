# knowledge-layer-core 0.44.0

## Canonical transformation semantics

- Added evidence-based classification for `identity`, `normalized`, `formatted`, `hashed`, `combined`, `derived`, `extracted` and `unknown` direct value-flow edges.
- Added exact field rename semantics: a rename is published only when both endpoints are observed field nodes and their terminal property names differ.
- Added stable grouping for observed derivations with `derivation_id`, `derivation_kind` and `derivation_source_count`.
- Propagated the same derivation identity from direct expression contributors to the direct expression-to-target edge.
- Added `transformation_basis` and derivation classification basis to the canonical edge payload.
- Classified static Java constants as constant nodes so they cannot be mistaken for renamed source attributes.
- Kept all classification repository-, class-, method- and field-neutral.

## Schema

- package: `knowledge-layer-core 0.44.0`
- suite schema: `knowledge_layer_suite_scope/v12`
- direct graph schema: `repository_value_flow/v2`

## Validation

A real `OmsToIndividualMapper.java` from `gw-sberid-update-phone-flags` was processed through
`code-analyzer-core 0.40.9` and this KLC version:

- 870 core field occurrences -> 870 value nodes;
- 626 core direct field-flow edges -> 626 direct value-flow edges;
- direct field renames such as `name.nonStandartizedSurname -> type.familyName` remained identity/preserved;
- `dateFormat.format(...)` was classified as formatted/partially preserved;
- `toCode(...)` was classified as derived/transformed;
- `Boolean.TRUE` was typed as a constant and did not claim a rename.

The real source is a validation case only. No special rule names that repository, class,
method or field.
