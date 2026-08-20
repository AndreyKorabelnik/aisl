# Test results — knowledge-layer-core 0.54.0

## Targeted tests

Executed:

- `tests/test_code_declared_model_builder.py`
- `tests/test_materialization_contracts.py`
- `tests/test_offline_validation.py`
- `tests/test_contracts.py`

Result: **35 passed**.

## Real runtime smoke

Input: actual `static_repository_analysis_run_manifest/v1` produced by Runner 0.9.46.

Result:

- build status: `complete`;
- source units: 3;
- types: 3;
- fields: 5;
- inheritance records: 1;
- type references: 2;
- effective fields: 6;
- declared field-type relationships: 1;
- gaps: 0;
- legacy `code_conceptual_model/v2` consumed: `false`.

## Additional checks

- `compileall knowledge_layer_core`: passed.
- materialization-contract CLI export from Core 0.43.26 contracts: passed.
- deterministic JSON/Markdown contract export: passed.
- full regression: intentionally not run; the legacy data-model path is not supported by the new materialization and was not revalidated.
- wheel: intentionally not built.
