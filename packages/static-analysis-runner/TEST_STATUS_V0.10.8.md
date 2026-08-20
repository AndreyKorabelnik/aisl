# Test status — static-analysis-runner 0.10.8

## Targeted/contract tests
- `tests/test_knowledge_planning.py`
- `tests/test_knowledge_execution_planning.py`
- `tests/test_knowledge_materialization_executor.py`
- `tests/test_knowledge_execution.py`
- Result with current KLC 0.59.32 available on PYTHONPATH: **48 passed**.

An earlier run without KLC on PYTHONPATH produced 8 environment failures (`ModuleNotFoundError: knowledge_layer_core`) and 40 passes; no code change was made for those environment failures.

## Real current-contract planning smoke
Inputs: real UCPDataModel + UCP TSA + datamart_profile_fl + explicit PDM artifact.
Selected user knowledge: `data-model-attribute-extension` only.

Result:
- catalog: 17 user-facing knowledge types, 3 internal materializations, 0 uncatalogued materializations;
- implicit public dependencies: code-declared-data-model, physical-data-model, sql-source-inventory;
- automatic internal dependencies: model-storage-semantics, logical-storage-mapping;
- execution plan: **ready**;
- blocking diagnostics: **0**;
- execution nodes: 11 = 5 Core analyzers + 6 KLC materializations;
- `model-storage-evidence/v1` is selected automatically from the internal dependency.

## Real runtime smoke
The canonical product runtime was started on the same real inputs.
Confirmed before external command timeout:
- UCPDataModel Core batch completed/partial with java-type-structure + model-storage evidence;
- UCP TSA Core batch completed with java-type-structure + model-storage evidence;
- model-storage-semantics materialization was automatically scheduled and atomically published in the follow-up materialization run.

The heavy SQL materialization exceeded the shell execution time budget before the full fresh end-to-end run completed. This is recorded as **not fully re-run**, not as a framework failure. A complete real E2E will be performed after the next agent-ready KLC projection step so the expensive SQL analysis is not repeated unnecessarily.

## Compile/package
See final handoff; compileall, source manifest, clean unzip/import and ZIP integrity are checked after final packaging.
