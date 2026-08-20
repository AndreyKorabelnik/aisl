# knowledge-layer-core 0.59.17

## Change
Adds derived workflow-resolved target-column lineage for SQL workflows whose final target is supplied by an observed `main_table_name` binding rather than an explicit SQL write target.

New derived tables:
- `sql_workflow_target_column_lineage`
- `sql_workflow_target_lineage_gap`

`KnowledgeLayerQuery.list_sql_target_column_lineage()` now projects this already-materialized lineage when the existing target resolver confirms exactly one physical target relation. Existing direct `sql_recursive_column_lineage` remains unchanged and is returned as before.

`get_sql_field_calculation()` automatically consumes the same combined lineage surface.

No target-name guessing, fuzzy matching or API-layer inference was added.

## Real validation
On `datamart_profile_fl`, target `custom_b2c_profile_fl.epk_client`:
- 116 lineage paths
- 86 target columns with lineage
- 7 explicit unresolved target-column gaps
- `active_flag`, `first_name`, `birth_dt`, `epk_client_status` resolved to observed sources

The remaining gaps are service/technical columns (`ctl_*`, row validity/update dates, partition field).
