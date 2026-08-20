# Test status — static-analysis-runner 0.10.9

## Targeted/contract regression

Using current KLC 0.59.33 on PYTHONPATH:
- `tests/test_knowledge_planning.py`
- `tests/test_knowledge_execution_planning.py`
- `tests/test_knowledge_materialization_executor.py`
- `tests/test_knowledge_execution.py`

Result: **48 passed**.

## Real current-contract planning smoke

Inputs:
- real UCP Data Model source;
- real UCP TSA source;
- real `datamart_profile_fl` source;
- explicit PDM typed artifact.

Selected user knowledge: `data-model-attribute-extension` only.

Result:
- plan status: **ready**;
- blocking diagnostics: **0**;
- executable nodes: **12 = 5 Core + 7 KLC**;
- automatically scheduled materializations include:
  - `model-storage-semantics`;
  - `logical-storage-mapping`;
  - `cross-artifact-data-model-mapping`;
  - `data-model-attribute-extension-context`.

No technical materialization ID is required in the user profile.

## Packaging

Compile/import, source manifest, clean unzip/import and ZIP integrity are verified during final packaging.

## Known limitation

This checkpoint validates planning/orchestration. The single final heavy real E2E of the complete product is intentionally performed after Runner 0.10.9 + KLC 0.59.33 are both fixed, to avoid repeatedly re-running expensive SQL analysis.
