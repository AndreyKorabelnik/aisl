# knowledge-api 0.18.4

## Change
The existing SQL target-column-lineage and field-calculation HTTP contracts now accept and expose workflow-resolved target mapping metadata produced by knowledge-layer-core 0.59.17.

No lineage inference was added to Knowledge API. The API remains a typed projection over KLC knowledge.

`SqlTargetColumnLineageSummary` adds:
- `by_target_mapping_status`
- optional `workflow_target_logical_name`
- optional `workflow_target_resolution_status`

## Real acceptance
For `custom_b2c_profile_fl.epk_client` on the real datamart artifact:
- target candidates: `confirmed_unique`
- target-column-lineage: HTTP 200, 116 paths, 86 target columns, 7 explicit gaps
- field-calculation: HTTP 200 / `complete` for `active_flag`, `first_name`, `birth_dt`, `epk_client_status`
