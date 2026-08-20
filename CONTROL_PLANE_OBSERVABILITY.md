# Knowledge Control Plane / Runner / KLC one-shot logging

Example:

```bash
knowledge-control-plane run ... --json > result.json
```

Final stdout remains JSON. Progress is visible on stderr and mirrored to:

```text
<runtime-root>/logs/jobs/<job-id>/run.log
```

The same progress stream now crosses Control Plane -> Runner -> isolated KLC worker. A long S2T run should therefore expose messages similar to:

```text
[runner_execution] Runner is executing the canonical Producer plan
[runner_execution] Executing Core evidence analyzers for ...
[runner_execution] [materialization:physical-model] started
[runner_execution] [materialization:physical-model] completed; duration=...
[runner_execution] [materialization:sql-analysis] started
[runner_execution] [materialization:sql-analysis][stderr] sql-analysis ingest started
[runner_execution] [materialization:sql-analysis][stderr] sql-analysis ingest sql_column_usage count=... duration=...
[runner_execution] [materialization:sql-analysis][stderr] sql-analysis workflow_context started
[runner_execution] [materialization:sql-analysis][stderr] workflow-context reference discovery ... duration=...
[runner_execution] [materialization:sql-analysis][stderr] sql-analysis workflow_target_lineage started
[runner_execution] [materialization:sql-analysis][stderr] workflow-target-lineage target=... fields=... duration=...
[runner_execution] [materialization:sql-analysis] completed; duration=...; counts=...
[runner_execution] [materialization:sql-target-source-mapping] started
...
```

Heartbeats remain useful when a subprocess itself emits no progress. RuntimeStore/SQLite remains canonical; text logs are observability mirrors only.
