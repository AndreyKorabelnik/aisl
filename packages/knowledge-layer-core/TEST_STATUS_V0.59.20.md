# Test status — knowledge-layer-core 0.59.20

## Executed

- `python -m compileall -q knowledge_layer_core tests` — PASS
- `pytest -q tests/test_sql_producer_lineage.py tests/test_cross_artifact_data_model_mapping.py tests/test_cross_artifact_workflow_dependency.py tests/test_materialization_contracts.py` — PASS: 16 passed

## Verified behavior

A synthetic integration scenario now proves:
`target.last_name -> physical staging.last_name -> observed producer query -> src.individual_name.surname`.
The ultimate target-source mapping is materialized even when no logical/Java source field can be bound.

## Known limitation / next step

Real `datamart_profile_fl / epk_client` has not yet been rebuilt with v0.59.20 in this chat. The next step is real validation against the supplied S2T Gold, especially `last_name`, `active_flag`, `epk_id`, `row_actual_from/to`, placeholders and display spelling, before exposing the compact Knowledge API surface.
