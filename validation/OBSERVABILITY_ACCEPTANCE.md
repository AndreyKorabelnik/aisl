# Observability acceptance

- `--json`: final stdout JSON remains parseable while progress goes to stderr.
- per-job run-log mirror path: `runtime/control-plane/logs/jobs/<job-id>/run.log`.
- heartbeat on silent stages.
- duration formatting.
- materialization count summaries.
- per-job mirror I/O failure does not fail canonical RuntimeStore log append.

Covered by `tests/test_one_shot_observability.py` and full KCP suite.
