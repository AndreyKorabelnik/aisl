# Changed files — static-analysis-runner 0.9.50

## Added

- `static_analysis_runner/knowledge_execution.py` — canonical execution of `knowledge_execution_plan/v1`.
- `schemas/knowledge_execution_result_v1.schema.json`.
- `tests/test_knowledge_execution.py`.
- `RELEASE_NOTES_V0.9.50.md`.
- `TEST_RESULTS_V0.9.50.md`.
- `HANDOVER_KNOWLEDGE_EXECUTION_V0.9.50.md`.

## Changed

- `static_analysis_runner/evidence_executor.py` — direct generic execution from an analyzer plan node and common Core request executor.
- `static_analysis_runner/knowledge_materialization_executor.py` — generic execution from materialization nodes in the combined plan.
- `static_analysis_runner/knowledge_execution_planning.py` — retains registration/materialization provenance for reusable existing inputs.
- `static_analysis_runner/cli.py` — canonical `knowledge-execute`; lower-level commands are marked diagnostic.
- `static_analysis_runner/execution_result_contracts.py` — current canonical execution result and next architectural step.
- `tests/test_evidence_executor.py`, `tests/test_knowledge_materialization_executor.py`, `tests/test_execution_result_contracts.py`, `tests/test_cli.py`.
- `README.md`, `docs/CLI.md`, `docs/CONTRACTS.md`.
- `static_analysis_runner/version.py`, `pyproject.toml` — version 0.9.50.
