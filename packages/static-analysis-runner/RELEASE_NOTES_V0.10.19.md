# static-analysis-runner 0.10.19

- Streams isolated KLC worker stdout/stderr into the existing Runner progress callback while preserving per-materialization stdout/stderr log files.
- Propagates the knowledge-execution progress sink through the generic materialization executor and isolated worker boundary.
- Emits materialization start/completion, duration, worker exit code, and available output counts.
- Removes the previous `capture_output=True` blind spot for long-running KLC materializations.
- No materialization-specific execution branch, semantic fallback, or second progress source of truth was added.
