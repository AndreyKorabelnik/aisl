# Test status — knowledge-layer-core 0.59.19

## Executed

- `python -m compileall -q knowledge_layer_core tests` — PASS
- `pytest -q tests/test_sql_producer_lineage.py tests/test_cross_artifact_data_model_mapping.py tests/test_cross_artifact_workflow_dependency.py` — PASS: 6 passed

## Scope

Targeted regression only. Full KLC regression was intentionally not run for this extraction-only logical step.

## Known limitation / next step

The reusable traversal is currently consumed by cross-artifact value-origin materialization. The SQL target-column API still reads the SQL-only lineage artifact and therefore still stops at physical staging relations. The next step is to materialize an ultimate S2T mapping in the cross-artifact KLC result using this shared traversal, then expose that ready knowledge through Knowledge API.
