# Analysis Execution Result Contract v1

- Runner version: `0.9.42`
- Catalog schema: `analysis_execution_result_catalog/v1`
- Contract: `analysis_execution_result_contract/v1`
- Execution effect: `none`
- Fingerprint: `b32a8b80f962dee8fa00a821d63d77f32c2fc5f7a2f88c5f46af990d7ab1b04c`

## Target boundary

- Core owns the meaning and schema of typed evidence artifacts.
- Runner owns execution, retries, lifecycle and artifact registration.
- KLC owns evidence selection and knowledge materialization.
- Task, Suite and Profile may be retained as request/provenance, but never define artifact meaning.

## Current assessment

- Current manifest variants: **4**
- Fully compliant variants: **0**
- Variants with any typed artifact registry: **1**
- Variants with direct or indirect Foundation identity: **2**
- Task-semantic-coupled variants: **3**
- Current KLC task-semantic routes: **8**

## Manifest gaps

### `static_repository_analysis_run_manifest/v1`

Scope: `repository_profile`. Target compliance: `partial`.

- does not enumerate requested or executed public analyzers
- does not register general evidence artifacts by artifact_kind and schema_version
- Foundation reference records path/request only and not a validated Foundation fingerprint
- non-SQL evidence semantics remain delegated to the Core repository manifest and file layout
- retry attempts are not represented for direct profile execution

### `analysis_suite_run_manifest/v1`

Scope: `repository_suite`. Target compliance: `partial`.

- does not record repository revision/content fingerprint directly
- does not enumerate public analyzers executed inside each profile
- does not register typed evidence artifacts produced by each analyzer
- task_id and task output directories remain the practical artifact-discovery boundary
- capabilities are copied from downstream manifest but current KLC production remains partly Task-coupled

### `static_workspace_analysis_run_manifest/v2`

Scope: `workspace`. Target compliance: `partial`.

- typed evidence is not aggregated into one workspace artifact registry
- analyzer and Foundation identities are indirect through nested repository/suite manifests
- workspace completion does not itself prove required evidence availability for a materialization
- suite-mode semantics inherit task_id-coupled artifact discovery

### `analysis_suite_run_manifest/v1` (portfolio_topology_repository_result)

Scope: `portfolio_repository`. Target compliance: `low`.

- reuses the suite manifest schema for a specialized non-suite result
- selects portfolio topology evidence through task_id=portfolio-topology
- does not expose a typed repository-interface-catalog evidence registration
- profile and artifact identities are incomplete on failed results

## Main conclusion

Runner already records lifecycle and retries reasonably well, but it cannot yet tell KLC what evidence exists without Task/profile/file-layout knowledge. The missing runtime boundary is a typed evidence artifact registry, not another redesign of Task or Suite.

## Revised next steps

1. **`conceptual_model_evidence_sufficiency/v1`** — Determine exact independent facts and schemas required by the first migration before changing runtime manifests.
2. **`conceptual_model_typed_evidence_contracts/v1`** — Define only the concrete structure, persistence and mapping artifacts proven necessary for the first vertical slice.
3. **`vertical_runtime_registration`** — Core publishes those typed artifacts and Runner registers them in analysis_execution_result/v1; do not build a universal registry spec beyond proven needs.
4. **`vertical_klc_import_and_task_decoupling`** — KLC imports the new artifacts by artifact_kind + schema_version and removes task_id semantics for conceptual-data-model in the same change.
5. **`parallel_parity_and_switch`** — Build KLC conceptual model beside the old Core output, compare, switch consumers, then delete the old Core materialization without compatibility adapters.
6. **`generalize_execution_result_runtime`** — Generalize the Runner registry and clean Profile/Task/Suite only after the first vertical slice proves the contract shape.

## Explicitly deferred

- broad removal of all task_id routes before typed evidence exists
- universal evidence envelope implementation for every current stage
- Task/Suite redesign
- caching, DAG execution and suite-local reuse
