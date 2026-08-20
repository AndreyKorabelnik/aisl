# Test status — knowledge-layer-core 0.59.46

## Targeted / contract tests

PASS — 20 tests:

- `tests/test_cross_artifact_data_model_mapping.py`
- `tests/test_attribute_extension_context.py`
- `tests/test_logical_storage_mapping_materialization.py`
- `tests/test_materialization_runtime.py`
- `tests/test_materialization_contracts.py`

Command result: `20 passed in 1.22s`.

## Compile/import

PASS — `python -m compileall -q knowledge_layer_core`.

## Representative real corrected knowledge workflow

Inputs: both UCP repositories (`UCPDataModel` + `UCPucp-tsa-v4`), real `datamart_profile_fl` SQL knowledge, and real PDM knowledge.

`logical-storage-mapping` (0.59.45 code retained in 0.59.46):

- status: completed
- entity mappings: 723
- relationship mappings: 488
- gaps: 0
- fuzzy matching: false

`cross-artifact-data-model-mapping` (0.59.46):

- status: completed
- elapsed inside materialization result: about 30 s
- storage/SQL mappings: 371
- logical-field/SQL usages: 1599
- workflow/PDM projection mappings: 470
- relation materializations: 626
- target/source mappings: 1305
- value-origin/physical lineage rows: 1078
- cross-artifact gaps: 0

`data-model-attribute-extension-context`:

- status: completed
- elapsed: 18.14 s
- object anchors: 1326
- join semantics: 1573
- context gaps: 1027
- join confidence: 462 confirmed / 86 strongly_supported / 1025 unresolved

The unresolved context is published explicitly and has not been suppressed or converted into inferred facts.

## Full regression

Not run for this small performance-only KLC cut. The broader Block 9 representative regression remains the last full multi-scenario regression; a new clean consumer deployment proof is still in progress.
