# Test results — knowledge-layer-core 0.53.9

## Scope

Read-only contract change only. Runtime ingestion, KLC materialization, query routing, capability publication and UI were not changed.

## Targeted regression

- `tests/test_materialization_contracts.py`
- `tests/test_suite_scope.py`
- `tests/test_physical_model_knowledge_layer.py`
- `tests/test_sql_analysis_knowledge_layer.py`
- `tests/test_portfolio_topology.py`

Result: **41 passed**.

## Contract-only check

`tests/test_materialization_contracts.py`: **10 passed**.

## Additional checks

- `compileall knowledge_layer_core`: passed.
- Real CLI export from Core 0.43.23 contracts: passed.
- Catalog schema: `knowledge_materialization_catalog/v2`.
- Planned materializations: 7.
- Legacy umbrella section routes: 27.
- Full regression: intentionally not run because runtime behavior is unchanged.
- Wheel: intentionally not built.
