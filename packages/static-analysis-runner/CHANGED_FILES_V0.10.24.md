# Changed files — Static Analysis Runner 0.10.24

- `static_analysis_runner/repository_acquisition.py` — shared repository-list selection and Runner-owned temporary acquisition root lifecycle.
- `static_analysis_runner/repository_batch.py` — generic sequential bulk execution of an existing repository-scoped Knowledge Profile; one independent execution result per repository with explicit partial failures and immediate checkout cleanup.
- `static_analysis_runner/cli.py` — `repository-batch-discover` and `repository-batch-run` commands.
- `static_analysis_runner/data_model_discovery.py` — reuses the generic repository acquisition primitives instead of owning duplicate selection/temp-run logic.
- `static_analysis_runner/knowledge_execution_planning.py` / `knowledge_planning.py` — conditional KLC capabilities are visible but are not hard expected outputs.
- tests and README — batch lifecycle, source selection, failure continuation and conditional-capability regressions.
- version metadata — 0.10.24.
