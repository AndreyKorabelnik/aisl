# Analysis Execution Result Contract v1

- Runner version: `0.9.44`
- Catalog schema: `analysis_execution_result_catalog/v1`
- Contract: `analysis_execution_result_contract/v1`
- Execution effect: `none`
- Fingerprint: `5807dacc85953235c774c8850b30bbb0096a9b4d61a766ee85b58b6504989c65`

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

1. **`knowledge_architecture_audit/v1`** — Use one generic Runner-owned audit to compare KLC knowledge requirements with Core evidence capabilities; begin with code-declared-data-model.
2. **`code_declared_data_model_typed_evidence_contracts/v1`** — Define only complete raw type, field, relationship, inheritance and gap evidence required by the first independent knowledge type.
3. **`vertical_runtime_registration`** — Core publishes typed code-declaration evidence and Runner registers it in analysis_execution_result/v1 without universalizing all analyzers.
4. **`vertical_klc_code_declared_import_and_task_decoupling`** — KLC imports typed code declarations by artifact_kind + schema_version and removes the matching legacy data-model Task semantics.
5. **`scoped_parity_and_switch`** — Compare only code-declared model semantics, switch consumers for that knowledge, and remove the corresponding legacy umbrella path without compatibility adapters.
6. **`logical_physical_mapping_vertical_slice`** — Add persistence mapping only after code-declared and physical models exist as independent knowledge.
7. **`effective_data_model_composition`** — Build the effective model last from independent KLC models while preserving source-layer provenance.

## Explicitly deferred

- broad removal of all task_id routes before typed evidence exists
- universal evidence envelope implementation for every current stage
- Task/Suite redesign
- caching, DAG execution and suite-local reuse
