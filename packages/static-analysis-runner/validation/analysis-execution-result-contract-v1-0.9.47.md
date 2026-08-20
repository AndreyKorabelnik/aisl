# Analysis Execution Result Contract v1

- Runner version: `0.9.47`
- Catalog schema: `analysis_execution_result_catalog/v1`
- Contract: `analysis_execution_result_contract/v1`
- Execution effect: `none`
- Fingerprint: `ff0b62887971cdc393deceb97b3c87dc29bffa14c49ab8ffbf456bba39fef73b`

## Target boundary

- Core owns the meaning and schema of typed evidence artifacts.
- Runner owns execution, retries, lifecycle and artifact registration.
- KLC owns evidence selection and knowledge materialization.
- Task, Suite and Profile may be retained as request/provenance, but never define artifact meaning.

## Current assessment

- Current manifest variants: **5**
- Fully compliant variants: **1**
- Variants with any typed artifact registry: **4**
- Variants with direct or indirect Foundation identity: **2**
- Task-semantic-coupled variants: **3**
- Current KLC task-semantic routes: **7**

## Manifest gaps

### `static_repository_analysis_run_manifest/v1`

Scope: `repository_profile`. Target compliance: `partial`.

- only java-type-structure-evidence and SQL have narrow typed registration; other analyzers are not yet registered
- Foundation reference records path/request only and not a validated Foundation fingerprint
- retry attempts are represented as one shared Core-process attempt rather than independent analyzer processes

### `analysis_suite_run_manifest/v1`

Scope: `repository_suite`. Target compliance: `partial`.

- does not record repository revision/content fingerprint directly
- does not aggregate duplicate task-local evidence into one suite-level canonical artifact registry
- only the first Java typed artifact is registered; other public analyzers remain profile-process-only
- task_id and task output directories remain the practical discovery boundary for legacy artifacts
- capabilities are copied from downstream manifest but current KLC production remains partly Task-coupled

### `static_workspace_analysis_run_manifest/v2`

Scope: `workspace`. Target compliance: `partial`.

- typed evidence remains indirect through nested repository/suite manifests and is not aggregated at workspace scope
- analyzer and Foundation identities are indirect through nested repository/suite manifests
- workspace completion does not itself prove required evidence availability for a materialization
- suite-mode semantics inherit task_id-coupled artifact discovery

### `knowledge_materialization_execution_run/v1`

Scope: `knowledge_resolution_plan`. Target compliance: `complete`.

- only KLC materializations registered in knowledge_materialization_runtime/v1 can execute
- repository and workspace analysis commands do not yet compile and invoke this plan automatically
- remaining evidence families require their own Core contracts and runtime publication

### `analysis_suite_run_manifest/v1` (portfolio_topology_repository_result)

Scope: `portfolio_repository`. Target compliance: `low`.

- reuses the suite manifest schema for a specialized non-suite result
- selects portfolio topology evidence through task_id=portfolio-topology
- does not expose a typed repository-interface-catalog evidence registration
- profile and artifact identities are incomplete on failed results

## Main conclusion

Runner now has one contract-driven Knowledge Materialization Executor. It topologically executes any KLC materialization registered behind knowledge_materialization_runtime/v1 and never imports a materializer-specific function.

## Revised next steps

1. **`generic_knowledge_materialization_executor/v1`** — Runner resolves contracts, orders dependencies, invokes one generic KLC entrypoint and records outputs/capabilities.
2. **`knowledge_profile_runtime_compilation`** — Compile user Knowledge Profile plus source availability into executable Core analyzer and KLC materialization plans.
3. **`logical_physical_mapping_evidence_and_materializer`** — Add the next independent knowledge without changing Runner executor code.
4. **`observed_storage_usage_evidence_and_materializer`** — Publish observed usage as separate knowledge through the same executor.
5. **`effective_data_model_composition`** — Register a composite KLC materializer over independent knowledge artifacts.
6. **`remove_remaining_task_suite_semantic_routes`** — Delete old orchestration only after each knowledge capability has a typed replacement.

## Explicitly deferred

- UI implementation
- caching and DAG optimization
- parallel materialization execution
- universal conversion of all current Core stages in one iteration
