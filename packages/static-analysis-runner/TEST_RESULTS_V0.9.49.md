# Test results — static-analysis-runner 0.9.49

## Focused source-tree checks

The iteration changes only knowledge planning, its contracts, architecture audit bindings and CLI exposure. A full Runner regression was intentionally not executed.

Focused command set:

- CLI contract tests;
- knowledge catalog/profile planning tests;
- knowledge architecture audit tests;
- new input-inventory and execution-plan tests;
- generic Core evidence executor tests;
- execution-result contract tests;
- generic KLC materialization executor tests.

Result: **53 passed in 6.90s**.

Additional checks:

- `compileall`: passed;
- JSON Schema validation for both new contracts: passed;
- canonical fingerprint validation: passed;
- graph endpoints/topological/execution-order validation: passed;
- real Core 0.43.27 + KLC 0.54.1 catalog smoke: `ready`;
- planned execution nodes: 2 (`java-type-structure-analyzer`, `code-declared-data-model`);
- blocking diagnostics in the real smoke: 0;
- transitional fields `future_analyzer_id`, `current_core_stage_ids`, `core_stage_sources` and `task_suite_profile_policy`: absent from generated current contracts;
- evidence-family names in Runner production code: absent.

The existing KLC materialization smoke was executed with the supplied KLC 0.54.1 source and DuckDB 1.5.5 wheel. No network dependency was required.

## Why no full regression

This release does not change repository cloning, Core process execution, workspace aggregation, topology, SQL parsing, KLC materialization implementation or UI/API consumers. Broad regression is reserved for the next iteration, where the two existing executors will be joined behind `knowledge-execute` and the old product route for `code-declared-data-model` will be deleted.

## Known limits

- `knowledge_execution_plan/v1` is compiled and validated but is not yet executed by one combined command.
- The current real Core catalog registers one evidence producer.
- The current real KLC runtime registers one materialization handler.
- Existing repository/workspace orchestration remains in the source tree until each knowledge family is migrated; the new planner never invokes it as fallback.
