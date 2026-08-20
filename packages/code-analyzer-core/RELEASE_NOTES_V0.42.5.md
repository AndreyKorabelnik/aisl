# Release notes — code-analyzer-core 0.42.5

Version 0.42.5 distinguishes generated structured values from physical SQL sources.

## Changes

- Added explicit `generated` relations for `LATERAL VIEW` / `EXPLODE` output aliases.
- Multipart column references are resolved by the leftmost proven relation alias while preserving the remaining structured field path.
- Nested CTE references such as `pad.pr.status` now bind to relation alias `pad` and retain field path `pr.status`.
- Unqualified LATERAL output aliases resolve to generated relations; ordinary unqualified columns still bind to the sole non-generated source.
- Generated fields are never published as physical or physical-template source fields.
- SQL profile implementation version is now `1.6`.

## Real repository effect

On `datamart_profile_fl`:

- `alias_unresolved` column usages: 95 -> 0;
- resolved column usages: 10,626 -> 10,721;
- generated relations: 8;
- column usages bound to generated relations: 27;
- false physical fields `address_dirty_key`, `electronic_address_dirty_key`, and `subProductLists` are no longer attributed to source tables;
- source JSON path `parsed_data.participantResults.participantResults` is retained as the physical input field.

The unchanged SQL Source Inventory fixture remains fully green: 30/30 cases and 100% relation, classification, field, and role quality gates.
