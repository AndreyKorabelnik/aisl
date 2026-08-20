# knowledge-layer-core 0.59.12

## Purpose
Compose already observed logical/storage, SQL workflow/materialization, projection and PDM facts into end-to-end data-model lineage.

## Changes
- Added generic script materialization composition from structured script-call facts plus resolved workflow bindings.
- Added strict SELECT/CTE/wildcard propagation using observed relation/projection graph.
- Materialization traversal is scoped to the same workflow context to avoid cross-workflow false paths.
- Added `cross_artifact_logical_field_physical_lineage`.
- No fuzzy field matching and no UCP/datamart-specific names.

## Real validation
- Script materialization rows: 235.
- End-to-end logical-field→physical-column lineage rows: 334.
- Distinct logical fields represented: 94.
- Distinct target PDM columns represented: 138 across 10 tables.
- `PhoneNumber.phoneNumber → epk_client_phonenumber.phone_number` reproduced as current and history paths.
- Targeted KLC tests: 17/17 passed.
- `compileall`: passed.

## Known limitation / next Gold gap
`BirthPlace.value → epk_client.birth_place` is not yet reproduced because the current workflow reachability graph for `epk_client` does not include the specialized `prep_stg_epk_client_birthplace.sql` chain. This is tracked as a workflow-reachability/composition gap, not as a SQL parser rewrite.
