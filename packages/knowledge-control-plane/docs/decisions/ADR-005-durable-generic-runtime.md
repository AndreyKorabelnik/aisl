# ADR-005: durable generic runtime

Status: accepted.

## Context

The canonical generic API from iteration 2 required an executable backend that could survive restarts, expose real-time logs and invoke framework tools without reproducing their internal logic.

The old UI backend stores most running state in process memory and combines HTTP routing, Git operations, subprocess execution, report handling and assistant behavior in one module. Reusing that structure would preserve the coupling we intend to remove.

## Decision

Implement a new backend under `src/knowledge_control_plane/runtime` with these boundaries:

- FastAPI route handlers call application services;
- SQLite stores runtime metadata only;
- `JobManager` owns state transitions and recovery;
- `CommandBuilder` invokes only public CLI contracts;
- `ProcessExecutor` uses argv execution without a shell;
- `ArtifactRegistry` exposes registered IDs rather than arbitrary paths;
- live updates use durable SSE cursors;
- legacy backend and frontend remain byte-identical until frontend migration.

Do not import internal classes from sibling framework packages. Do not merge the data-model namespace into the generic router.

## Consequences

- generic jobs and logs survive backend restarts;
- an interrupted running job becomes an explicit retryable failure rather than silently remaining active;
- output safety is enforced before execution;
- large artifacts are not loaded fully into memory for hashing or preview;
- the old UI remains operational but does not benefit from the new backend until iteration 4;
- full pipeline orchestration and remote checkout remain separate future capabilities rather than being hidden inside the first job implementation.
