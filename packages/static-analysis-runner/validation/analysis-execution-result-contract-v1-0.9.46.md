# Analysis Execution Result Contract v1

- Runner version: `0.9.46`
- Catalog schema: `analysis_execution_result_catalog/v1`
- Contract: `analysis_execution_result_contract/v1`
- Execution effect: `none`
- Fingerprint: `b3dd9e18d30e0a88cf4d96806828be218674b5c1094fff93c018502c03c947a0`

## Target boundary

- Core owns the meaning and schema of typed evidence artifacts.
- Runner owns execution, retries, lifecycle and artifact registration.
- KLC owns evidence selection and knowledge materialization.
- Task, Suite and Profile may be retained as request/provenance, but never define artifact meaning.

## Current assessment

- Current manifest variants: **4**
- Fully compliant variants: **0**
- Variants with any typed artifact registry: **3**
- Variants with direct or indirect Foundation identity: **2**
- Task-semantic-coupled variants: **3**
- Current KLC task-semantic routes: **8**

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

### `analysis_suite_run_manifest/v1` (portfolio_topology_repository_result)

Scope: `portfolio_repository`. Target compliance: `low`.

- reuses the suite manifest schema for a specialized non-suite result
- selects portfolio topology evidence through task_id=portfolio-topology
- does not expose a typed repository-interface-catalog evidence registration
- profile and artifact identities are incomplete on failed results

## Main conclusion

Runner now validates and registers the first self-describing Core evidence artifact without using Task as semantic identity. The next boundary is KLC import/materialization for code-declared-data-model; broad Runner registry generalization remains deferred.

## Revised next steps

1. **`knowledge_architecture_audit/v1`** — One generic Runner-owned audit now evaluates every catalogued knowledge type.
2. **`code_declared_data_model_typed_evidence_contracts/v1`** — Core defines the complete uncapped java-type-structure-evidence/v1 contract.
3. **`vertical_runtime_registration`** — Core publishes and Runner validates/registers java-type-structure-evidence/v1 without Task-based semantic identity.
4. **`vertical_klc_code_declared_import_and_task_decoupling`** — KLC must import the registered artifact by artifact_kind + schema_version and materialize code-declared-data-model.
5. **`scoped_parity_and_switch`** — Compare only code-declared model semantics, switch consumers, and remove the matching legacy route.
6. **`logical_physical_mapping_vertical_slice`** — Add persistence mapping after code-declared and physical models exist independently.
7. **`effective_data_model_composition`** — Build the effective model last from independent KLC models while preserving provenance.

## Explicitly deferred

- broad removal of all task_id routes before typed evidence exists
- universal evidence envelope implementation for every current stage
- Task/Suite redesign
- caching, DAG execution and suite-local reuse
