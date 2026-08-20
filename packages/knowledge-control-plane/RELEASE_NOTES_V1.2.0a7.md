# Knowledge Control Plane 1.2.0a7

## One-shot observability

- `knowledge-control-plane run --json` keeps final stdout machine-readable while live progress is always emitted to stderr.
- Canonical job logs are mirrored to `runtime/control-plane/logs/jobs/<job-id>/run.log`; RuntimeStore/SQLite remains the source of truth.
- Long silent one-shot stages emit canonical heartbeat log entries (default 30 seconds, configurable via `KNOWLEDGE_CONTROL_PLANE_HEARTBEAT_SECONDS`).
- Successful stages report elapsed duration; failures include elapsed duration when available.
- Runner artifact scan has explicit start/completion logs with registered artifact count and duration.
- Materialization receipts with `output.counts` are summarized into the runner-execution log.
- Failure to write the human-readable per-job log mirror does not fail the knowledge execution.

No Producer/Core/Runner/KLC/Knowledge API/Assistant semantics changed.
