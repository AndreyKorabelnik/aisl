# knowledge-layer-core 0.27.0

Iteration 22 replaces the ambiguous flattened consumer relationship payload with a canonical nested contract.

## Changes

- `DataModelQueryService.get_relationships()` and `get_join_guidance()` return the same canonical relationship objects.
- Added explicit `source`, `target.logical_identity`, `target.storage_key`, `reference.encoding_inputs` and structured `join` sections.
- Removed emitted legacy payload fields such as `join_guidance` and `target_key_fields`.
- Logical identity/version roles cannot be interpreted as a physical storage key when observed storage-key evidence exists.
- Physical encoding remains `downstream_interpretation_required`; KLC does not add alias normalization, separators, SQL or UCP-specific rules.
- Physical FK/column relationships can use the same nested contract downstream with `physical_join_confirmed=true`.
