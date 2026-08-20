# Release notes — static-analysis-runner 0.9.47

## Generic Knowledge Materialization Executor

Runner now executes any materialization selected by `knowledge_resolution_plan/v2` through one contract-driven implementation. It does not import a KLC builder per knowledge type and does not branch on `knowledge_id` or `materialization_id`.

The executor:

- validates plan and KLC catalog fingerprints;
- resolves registered evidence by `artifact_kind + schema_version`;
- resolves dependent knowledge artifacts from materialization contracts;
- topologically orders materializations;
- invokes the single KLC `knowledge_materialization_runtime/v1` entrypoint;
- records `materialization_executions` and `knowledge_artifacts`;
- publishes capabilities only after successful KLC results.

KLC owns its materializer registry and domain algorithms. Missing evidence, knowledge dependencies or runtime registration fail explicitly. Legacy Task-directory discovery, fallback and dual-write are not supported.

`code-declared-data-model` is the first real materialization executed through this generic mechanism; it is not hard-coded in Runner.
