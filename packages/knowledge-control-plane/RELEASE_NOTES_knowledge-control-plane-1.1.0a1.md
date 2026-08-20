# Knowledge Control Plane 1.1.0a1

## Scope

Adds the backend MVP for automatic Prepared Knowledge freshness and refresh without creating a second scheduler, producer, planner, job engine, or publication path.

## Added

- Durable Production Registration: system + Knowledge Profile + selected repositories + optional physical model + refresh policy.
- Git tracked refs for remote repository registrations (`HEAD`, branch, or explicit ref).
- Immutable source snapshots with Git commit SHA or file SHA-256 provenance.
- Freshness states: `up_to_date`, `change_detected`, `stale`, `update_queued`, `update_running`, `update_failed`, `source_unavailable`.
- `FreshnessService` that compares current immutable snapshots with the last successfully published baseline.
- Configuration-revision baseline: profile/parameters/source-set/PDM/report-policy changes trigger rebuild even when Git commits are unchanged.
- Job-local detached checkout at the exact resolved commit for both local and remote Git inputs.
- Job-local PDM copy with SHA-256 verification before Runner execution.
- Production/source snapshot provenance attached to JobDetails and published Knowledge API revision metadata.
- HTTP Production Registration CRUD and refresh-check endpoints.
- `knowledge-control-plane refresh-check --due` / `--production` scheduler-facing CLI; it calls the running Control Plane HTTP API rather than opening a second runtime over SQLite.

## Preserved ownership

- Control Plane decides *whether* a registered production is stale and creates an ordinary knowledge-execution job.
- Runner still owns profile validation, dependency resolution, execution planning/DAG, and execution.
- Core and KLC production mechanisms are unchanged.
- Knowledge API remains the sole Prepared Knowledge publication/read boundary.
- No internal periodic daemon/scheduler was added.

## Failure semantics

- Failed/cancelled refresh does not move the successful source baseline.
- Unavailable/dirty sources are explicit `source_unavailable`, never `up_to_date`.
- A newer source revision observed while a pinned refresh is running is not run concurrently; the pinned job finishes, then the next check detects the newer revision.
- A source that changes between freshness resolution and acquisition fails with a visible snapshot mismatch rather than silently analyzing a different revision.
