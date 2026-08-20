# analysis-ui 2.0.0a3

Iteration 3 implements the durable generic orchestration backend defined by generic API v1 while preserving the UI2 1.4.7 runtime unchanged.

## Added

- SQLite runtime persistence for configuration, repositories, workspaces, jobs, logs, events, artifacts and conversations;
- persistent `JobManager` with queueing, state transitions, cancellation, retry and restart recovery;
- safe argv-only `ProcessExecutor` with stdout/stderr streaming, process-group cancellation and timeout support;
- fixed command adapters for repository analysis, workspace analysis, low-level Knowledge Layer materialization and report builds;
- workspace repository-selection materialization through runtime-owned symlinks;
- output-root validation and ownership markers;
- SSE event streaming with durable numeric cursors;
- artifact registry with streaming SHA-256, bounded text preview and downloads;
- capability/version/configuration/repository/workspace/profile/job/artifact runtime endpoints;
- secret-name rejection in job parameters and environment-secret redaction in captured logs;
- `analysis-ui serve` CLI;
- runtime architecture, operations guide and ADR-005;
- integration tests for successful execution, cancellation, retry, restart recovery, output safety, secret redaction and data-model route coexistence.

## Preserved

- all 50 UI2 1.4.7 runtime files remain byte-identical;
- all six protected data-model routes remain outside the generic router;
- DuckDB remains the Knowledge Layer artifact format.

## Deliberately deferred

- Vue frontend migration to the generic API;
- multi-stage full pipeline execution;
- checkout of registered remote repositories;
- generic assistant question execution.
