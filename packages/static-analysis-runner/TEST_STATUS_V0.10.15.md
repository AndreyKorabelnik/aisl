# Test status — static-analysis-runner 0.10.15

## Targeted / contract tests

PASS — 52 tests:

- `tests/test_knowledge_execution.py`
- `tests/test_knowledge_execution_planning.py`
- `tests/test_knowledge_materialization_executor.py`
- `tests/test_knowledge_planning.py`

Command result with DuckDB 1.5.5 available to isolated KLC workers: `52 passed in 14.54s`.

An earlier invocation without DuckDB on the subprocess `PYTHONPATH` produced 45 passes and 7 identical environment failures (`DuckDB runtime is unavailable`). No code change was made for those environment failures; the suite was rerun in the correct producer test environment and passed completely.

## Compile

PASS — `python -m compileall -q static_analysis_runner tests`.

## Real Prepared Knowledge portability proof

PASS for the changed contract surface.

Real inputs:

- UCPDataModel;
- UCPucp-tsa-v4;
- datamart_profile_fl;
- PDM_B2C_restored typed physical-model artifact.

The generic Runner completed `data-model-attribute-extension` with status `completed` using Runner 0.10.15 and KLC 0.59.46. Produced Knowledge Layer artifact locations inside `knowledge_execution_result/v1` are relocatable relative locations.

The completed Prepared Knowledge directory was copied to a separate Consumer deployment root and successfully validated/published by Knowledge API 0.26.2. The active publication exposes the expected UCP/SQL/PDM attribute-extension capabilities without Core or Runner installed in the Consumer environment.

## Scope

The 0.10.15 code change only normalizes produced Knowledge Layer `output_path` and `manifest_path` through the existing relative-or-absolute helper. It does not change execution planning, materialization semantics, publication semantics, discovery, or add a fallback.

Full Runner regression was not rerun for this narrow portability cut; the last broad baseline remains Block 9.
