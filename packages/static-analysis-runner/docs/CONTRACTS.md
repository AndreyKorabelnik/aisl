# Contracts

## Analysis contract

Every repository or workspace run declares exactly one analysis contract:

```json
{"kind": "profile", "profile_id": "...", "sha256": "..."}
```

or:

```json
{"kind": "suite", "suite_id": "...", "sha256": "..."}
```


## Repository identity

`code-analyzer-core` owns canonical repository-ID generation.

- a single-profile run consumes `repository-analysis-manifest.json -> repo_id`;
- a suite run consumes `foundation-manifest.json -> repository.repo_id` before starting task profiles;
- every suite task must publish the same canonical ID;
- suite Knowledge Layer `scope_id` equals that canonical ID;
- `requested_repo_id` is retained only for audit when the caller supplied `--repo-id`;
- workspace aggregation fails on canonical-ID collisions.

The runner does not maintain a second normalization algorithm for repository suite execution.

## Preselected repository registration

`selected_repositories_manifest/v2` records the input root, normalized repository IDs, selection mode and selected analysis contract.

`selected_repositories_resolved/v2` adds absolute paths, immutable revision fingerprints and completion artifacts. A completed row contains either:

- `repository_analysis_manifest` for profile mode; or
- `suite_manifest` for suite mode.

## Workspace aggregation

Profile mode converges to `candidate_selection_manifest/v1` and is consumed directly by `knowledge-layer-core`.

Suite mode publishes `workspace_suite_selection_manifest/v1` for audit and feeds the completed repository suite manifests directly to `knowledge-layer-core`.


## SQL repository artifact

A repository run routed to the SQL analyzer must publish:

```text
static-analysis-output/sql-analysis/manifest.json
```

The canonical contract is `sql-analysis/v1` with contract version `1.0`. The manifest
publishes an ordered list of typed JSONL streams with their ID fields, record counts,
byte sizes and SHA-256 digests. The runner validates every declared stream, but does
not own a fixed list or fixed count of streams. It validates:

- artifact, contract and schema versions;
- non-empty, unique fact types, paths and declared ID fields;
- safe repository-local shard paths;
- JSONL structure and unique IDs within each declared fact type;
- absence of machine-local evidence paths;
- count, size and digest metadata;
- coverage metadata and its digest;
- the aggregate content fingerprint calculated in manifest order.

`complete` and `partial` are valid analysis statuses. `partial` produces a warning.
Malformed or structurally inconsistent artifacts fail the repository run.

When `--materialize-knowledge` is requested, the runner calls the SQL builder exported
by `knowledge-layer-core`. KLC owns the typed import schema and rejects unsupported
stream sets explicitly; runner never silently discards an additive stream.

## Knowledge architecture audit

`knowledge_architecture_audit/v1` is owned by Runner and has no execution effect. It composes official declarations from:

- `knowledge_catalog/v2`;
- `knowledge_materialization_catalog/v2`;
- `core_analysis_catalog/v1`;
- `core_target_analysis_contracts/v1`;
- `core_evidence_contract_catalog/v1`;
- `analysis_execution_result_catalog/v1`;
- `core_klc_responsibility_map/v1`.

The audit evaluates readiness per `knowledge_id`, not per Task, Suite or Core Profile. It records source-observation availability, typed evidence contract state, runtime publication, Runner artifact registration, KLC materialization readiness and remaining legacy semantic routes.

## Knowledge input inventory

`knowledge_input_inventory/v1` is owned by Runner and describes only facts available to one planned execution. Its semantic categories are independent:

1. source snapshots and their languages/revisions;
2. existing typed evidence artifacts;
3. existing knowledge artifacts;
4. Core evidence contracts and analyzer registration;
5. KLC materialization contracts and handler registration.

A contract or registered producer is not treated as an available artifact. File-backed inputs must resolve to an existing location. The contract fingerprint covers the complete canonical payload.

## Knowledge execution plan

`knowledge_execution_plan/v1` is owned by Runner. It is compiled from:

- `knowledge_profile/v2` and `knowledge_catalog/v2`;
- `knowledge_input_inventory/v1`;
- `core_evidence_contract_catalog/v1`;
- `knowledge_materialization_catalog/v2`.

Its graph node kinds are:

- `source_snapshot`;
- `core_evidence_analyzer`;
- `typed_evidence_artifact`;
- `knowledge_materialization`;
- `knowledge_artifact`.

Evidence identity is `artifact_kind + schema_version`. Knowledge identity is `model_kind + schema_version + source_materialization_id`. The plan validator checks the fingerprint, unique graph identities, edge endpoints, topological order, executable order, status counters and semantic policy.

Task, Suite and Core Profile identifiers do not participate in semantic routing. There are no compatibility adapters, hidden fallback routes or dual-write outputs.

## Canonical knowledge execution result

`knowledge_execution_result/v1` is owned by Runner and is produced only by executing a validated `knowledge_execution_plan/v1`. It records:

- the plan and bound Core/KLC catalog fingerprints;
- exact execution order and per-node completion;
- Core analyzer executions and all registered typed evidence;
- every source repository registration manifest, including reused evidence provenance;
- KLC materialization executions and produced knowledge artifacts;
- capabilities from completed materializations only;
- semantic policy, timestamps, diagnostics and a canonical result fingerprint.

The executor checks source-snapshot freshness before Core execution. It rejects a changed source, catalog mismatch, blocked plan, unknown node, output mismatch, incomplete materialization or missing expected model/capability. Runner does not select a concrete analyzer or materializer: Core and KLC own those registries. Task, Suite and Core Profile semantics are excluded; compatibility adapters, fallback discovery and dual-write are unsupported.

## Generic Core evidence execution and registration

Runner 0.9.48 consumes two official inputs:

- `knowledge_resolution_plan/v2`;
- `core_evidence_contract_catalog/v1`.

It compiles Core-produced requirements into `core_evidence_execution_request/v1` and invokes the single Core `core_evidence_runtime/v1` entrypoint. Core owns the registry from semantic evidence identity to analyzer handler. Runner does not contain a registry or branch per evidence family.

The semantic identity is exactly:

```text
artifact_kind + schema_version
```

Core returns `core_evidence_execution_result/v1`. Runner validates request/result fingerprints, runtime identity, producer version, analyzer executions, source snapshots, artifact envelopes, content fingerprints, file digests and safe locations. It then publishes the typed artifacts in `static_repository_analysis_run_manifest/v1`.

Task, Suite, Profile and knowledge identifiers may appear only as execution-request provenance. The former Java-specific registration module, task-local prepared-artifact lookup and automatic evidence publication from the legacy repository path were removed. Compatibility adapters, fallback discovery and dual-write are unsupported.

## Generic knowledge materialization execution

`knowledge_materialization_execution_run/v1` is owned by Runner. Its inputs are:

- `knowledge_resolution_plan/v2`;
- `knowledge_materialization_catalog/v2` with `knowledge_materialization_runtime/v1`;
- Runner-registered typed evidence artifacts;
- optional completed KLC materialization results used as knowledge dependencies.

Runner performs only generic orchestration:

1. validates official fingerprints;
2. orders materializations from declared knowledge dependencies;
3. resolves evidence by `artifact_kind + schema_version`;
4. resolves knowledge dependencies by model kind, schema version and source materialization;
5. invokes the single KLC generic entrypoint with `materialization_id`;
6. records materialization executions and produced knowledge artifacts;
7. publishes capabilities only from completed KLC results.

Domain-specific materializer selection and implementation remain in the KLC-owned registry. Runner source must not contain materialization-specific dispatch branches. Task, Suite and Core Profile are excluded from semantic routing; legacy fallback and dual-write are unsupported.
