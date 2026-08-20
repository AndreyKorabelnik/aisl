# Changed files — 0.9.47

- `static_analysis_runner/knowledge_materialization_executor.py` — universal contract-driven executor for any KLC materialization registered behind `knowledge_materialization_runtime/v1`; typed evidence/knowledge resolution, dependency ordering, generic KLC invocation, execution/result registration and capability publication.
- `static_analysis_runner/cli.py` — generic `knowledge-materialize` command.
- `schemas/knowledge_materialization_execution_run_v1.schema.json` — Runner execution-run contract.
- `static_analysis_runner/execution_result_contracts.py` — generic executor recorded as completed and Knowledge Profile runtime compilation identified as the next orchestration layer.
- `static_analysis_runner/knowledge_architecture_audit.py` — KLC readiness based on generic runtime registration and generic next-step selection; no stale knowledge-specific recommendation.
- `tests/test_knowledge_materialization_executor.py` — generic execution, topological order, explicit missing-input failures, CLI and source-level absence of materialization-specific Runner branches.
- `tests/test_execution_result_contracts.py`, `tests/test_knowledge_architecture_audit.py` — updated common contract assertions.
- `README.md`, `docs/CLI.md`, `docs/CONTRACTS.md`, `docs/KNOWLEDGE_ARCHITECTURE_AUDIT.md` — universal execution boundary and no-legacy policy.
- `pyproject.toml`, `static_analysis_runner/version.py` — version 0.9.47.
