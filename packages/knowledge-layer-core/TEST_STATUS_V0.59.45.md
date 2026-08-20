# Test status — knowledge-layer-core 0.59.45

## Targeted / contract tests

PASS — 18 tests:

- `tests/test_logical_storage_mapping_materialization.py`
- `tests/test_attribute_extension_context.py`
- `tests/test_materialization_runtime.py`
- `tests/test_materialization_contracts.py`

Command result: `18 passed in 0.49s`.

## Compile/import

PASS — `python -m compileall -q knowledge_layer_core`.

## Representative real materialization

PASS — current UCPDataModel + UCPucp-tsa-v4 prepared inputs through the generic `logical-storage-mapping` materialization runtime.

Observed result:

- producer: knowledge-layer-core 0.59.45
- status: completed
- elapsed: 1.60 s
- peak RSS: 224500 KB
- entity mappings: 723
- relationship mappings: 488
- gaps: 0
- all entity rows bound: true
- all relationship rows bound: true
- fuzzy matching used: false
- name normalization used: false

The pre-change run using the same real input was externally terminated after 150 s while only 148/723 entity mapping rows had been committed. This is performance evidence, not a semantic baseline comparison.

## Full regression

Not run for this small local performance-only KLC change. Full representative regression remains the Block 9 baseline until the larger consumer-proof block is completed.
