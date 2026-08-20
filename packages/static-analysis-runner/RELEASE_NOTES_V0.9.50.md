# static-analysis-runner 0.9.50 — canonical knowledge execution

Runner now executes one validated `knowledge_execution_plan/v1` through the generic Core evidence and KLC materialization runtimes and publishes one canonical `knowledge_execution_result/v1`.

## Added

- `knowledge-execute` as the product entrypoint for the compiled DAG.
- `knowledge_execution_result/v1` and strict JSON Schema.
- Direct execution of Core analyzer nodes from the execution plan.
- Direct execution of KLC materialization nodes from the same plan.
- Source-snapshot freshness checks before Core invocation.
- Complete evidence, repository-manifest, materialization, knowledge-artifact and capability provenance.
- Reuse of already registered typed evidence without rerunning Core.

## Architectural rules

- Runner dispatches only by validated plan node kind and topological order.
- Core owns analyzer selection by typed evidence identity.
- KLC owns materializer selection by `materialization_id`.
- Capabilities come only from completed materialization results.
- Task, Suite and Core Profile semantics are not used.
- Legacy fallback, compatibility adapters and dual-write are unsupported.

The existing `evidence-execute` and `knowledge-materialize` commands are retained only as low-level diagnostic entrypoints. They are not part of the product route.
