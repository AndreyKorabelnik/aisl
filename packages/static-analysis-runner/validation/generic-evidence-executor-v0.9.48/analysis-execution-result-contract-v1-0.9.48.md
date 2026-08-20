# Analysis Execution Result Contract v1

- Runner version: `0.9.48`
- Catalog schema: `analysis_execution_result_catalog/v1`
- Contract: `analysis_execution_result_contract/v1`
- Execution effect: `none`
- Fingerprint: `aae8f317b43021c7bd30051acc4e6339ac7f9823359356d53e533f78ed669196`

## Target boundary

- Core owns the meaning and schema of typed evidence artifacts.
- Runner owns execution, retries, lifecycle and artifact registration.
- KLC owns evidence selection and knowledge materialization.
- Task, Suite and Profile may be retained as request/provenance, but never define artifact meaning.

## Current assessment

- Current manifest variants: **5**
- Fully compliant variants: **2**
- Variants with any typed artifact registry: **5**
- Variants with direct or indirect Foundation identity: **3**
- Task-semantic-coupled variants: **3**
- Current KLC task-semantic routes: **7**

## Manifest gaps

### `static_repository_analysis_run_manifest/v1`

Scope: `repository_evidence`. Target compliance: `full`.

- Foundation reuse is not yet compiled into the generic evidence request
- one Core process currently executes the complete evidence request

### `analysis_suite_run_manifest/v1`

Scope: `repository_suite`. Target compliance: `partial`.

- suite execution is not the target evidence selection boundary
- task composition remains execution provenance and must not select evidence semantics

### `static_workspace_analysis_run_manifest/v2`

Scope: `workspace`. Target compliance: `partial`.

- workspace evidence remains indirect through repository manifests
- workspace completion alone does not prove materialization input completeness

### `knowledge_materialization_execution_run/v1`

Scope: `knowledge_resolution_plan`. Target compliance: `full`.


### `portfolio_topology_run_manifest/v1`

Scope: `portfolio`. Target compliance: `partial`.

- topology workflow has its own compact evidence boundary and is not yet compiled from Knowledge Profile

## Main conclusion

Runner now has a contract-driven upper and lower execution path: Knowledge Resolution Plan requirements are compiled into the generic Core evidence runtime, registered as typed evidence, and then consumed by the generic KLC materialization runtime.

## Revised next steps

1. **`generic_knowledge_materialization_executor/v1`** — Runner resolves materialization contracts and calls one generic KLC runtime.
2. **`generic_core_evidence_runtime_and_executor`** — Runner compiles Core evidence requirements and registers arbitrary typed artifacts without evidence-family branches.
3. **`switch_consumers_to_generic_knowledge_execution`** — Knowledge API, Reporting, Assistant and UI still use the previous working integration path.
4. **`next_independent_evidence_and_materializer`** — Validate that a new evidence family requires only Core registration, contracts and a KLC materializer.

## Explicitly deferred

- UI implementation until backend consumers are switched
- caching and DAG optimization
- parallel evidence and materialization execution
- migration of every existing Core evidence family in one iteration
