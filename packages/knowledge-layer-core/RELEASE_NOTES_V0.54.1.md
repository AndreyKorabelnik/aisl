# Release Notes — knowledge-layer-core 0.54.1

Introduces `knowledge_materialization_runtime/v1`, a generic KLC-owned execution boundary.

Runner or another orchestrator now invokes KLC with a `knowledge_materialization_request/v1` containing only a materialization ID, scope and resolved typed inputs. KLC validates the request against its materialization contract, dispatches through its internal registry and returns `knowledge_materialization_execution_result/v1`.

The first registered materialization is `code-declared-data-model`. The generic boundary contains no Task, Suite or Core Profile semantics and provides no legacy fallback.
