# knowledge-layer-core 0.59.21

## Product S2T through observed SQL producers

Adds registered materialization `sql-target-source-mapping` producing `sql-target-source-mapping/v1`.
It composes the existing workflow target-column lineage through observed physical relation producers and publishes two deliberately separate layers:

- `sql_target_source_mapping` — complete raw/syntactic ultimate SQL origins with producer/materialization provenance;
- `sql_target_value_source_mapping` — deduplicated value origins, semantically normalised only when independent typed evidence proves equivalence.

Producer traversal uses observed script-call / SQL-write / workflow-copy materialisations and workflow dependencies. It never relies on `stg_*` naming or relation semantic-role heuristics.

For encoded storage keys, value-origin normalisation requires all of:
- structured SQL projection-expression path from Core evidence;
- unique exact flattened storage identity;
- observed storage-key parent relationship / exact parent-key binding;
- a unique direct ancestor SQL origin in the same target lineage and base/history representation.

Raw paths are never deleted or rewritten. If the semantic proof is incomplete, the raw origin remains explainable and an explicit semantic gap is published.

### Real `epk_client` validation

Using the supplied real datamart plus real TSA model-storage knowledge:
- observed relation producers: 626;
- workflow dependencies: 33;
- raw recursive target-source rows: 2103;
- `epk_client.epk_id` resolves to exactly two value origins: current/history `Individual.id`;
- `last_name` resolves to current/history `IndividualName.surname`;
- `active_flag` resolves to current/history `Individual.endDate`.

Known next defects are intentionally left explicit: `row_actual_from` and `row_actual_to` still stop earlier in `sql_workflow_target_column_lineage` with `workflow_target_projection_source_unresolved`; source schema placeholders are not yet presentation-resolved.
