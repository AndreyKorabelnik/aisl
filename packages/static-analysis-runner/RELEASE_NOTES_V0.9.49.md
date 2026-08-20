# static-analysis-runner 0.9.49 — knowledge execution planning

Runner now compiles a user Knowledge Profile and the inputs actually available for a run into one deterministic execution DAG.

## Added

- `knowledge_input_inventory/v1` separates contract existence, producer registration and actual run-time availability.
- `knowledge_execution_plan/v1` represents source snapshots, Core evidence analyzers, typed evidence, KLC materializations and knowledge artifacts in one graph.
- `knowledge-input-inventory` and `knowledge-execution-plan` CLI commands.
- Strict fingerprint and graph validation.

## Removed from current contracts

- `future_analyzer_id`;
- public Core stage bindings such as `current_core_stage_ids` and `core_stage_sources`;
- Task/Suite/Profile execution policy fields.

Core analyzers are resolved only through `core_evidence_contract_catalog/v1`; KLC handlers only through `knowledge_materialization_catalog/v2`. Missing inputs or runtime registrations produce blocking diagnostics. Legacy fallback, compatibility adapters and dual-write are unsupported.

This release plans but does not yet execute the combined DAG. The next iteration adds the single `knowledge-execute` entrypoint and `knowledge_execution_result/v1`.
