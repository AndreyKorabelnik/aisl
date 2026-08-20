# Changed files — static-analysis-runner 0.9.49

## Added

- `static_analysis_runner/knowledge_execution_planning.py`.
- `schemas/knowledge_input_inventory_v1.schema.json`.
- `schemas/knowledge_execution_plan_v1.schema.json`.
- `tests/test_knowledge_execution_planning.py`.
- `RELEASE_NOTES_V0.9.49.md`.
- `TEST_RESULTS_V0.9.49.md`.
- `HANDOVER_KNOWLEDGE_EXECUTION_PLANNING_V0.9.49.md`.

## Changed

- `static_analysis_runner/cli.py` — inventory and execution-plan commands.
- `static_analysis_runner/knowledge_planning.py` — current analyzer/runtime bindings replace transitional Core stage fields.
- `static_analysis_runner/knowledge_architecture_audit.py` — runtime readiness is derived from registered Core producers.
- `tests/test_knowledge_planning.py`, `tests/test_knowledge_architecture_audit.py`, `tests/test_cli.py`.
- `README.md`, `docs/CLI.md`, `docs/CONTRACTS.md`.
- `static_analysis_runner/version.py`, `pyproject.toml` — version 0.9.49.
