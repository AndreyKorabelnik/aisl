# Knowledge Control Plane operations — 2.0.0a65

## Start and diagnose

```bash
knowledge-control-plane doctor
knowledge-control-plane doctor --json
knowledge-control-plane serve --host 0.0.0.0 --port 8000
```

Default runtime paths:

```text
outputs/ui/knowledge-control-plane.sqlite3
outputs/ui/jobs/<job-id>/
outputs/static-analysis/<job-id>/
outputs/reports/<job-id>/
```

Configuration overrides:

```bash
export KNOWLEDGE_CONTROL_PLANE_RUNTIME_ROOT="/safe/path/outputs/ui"
export KNOWLEDGE_CONTROL_PLANE_ANALYSIS_OUTPUT_ROOT="/safe/path/outputs/static-analysis"
export KNOWLEDGE_CONTROL_PLANE_REPORT_OUTPUT_ROOT="/safe/path/outputs/reports"
export STATIC_ANALYSIS_RUNNER_COMMAND="static-analysis-runner"
export KNOWLEDGE_REPORTING_COMMAND="knowledge-reporting"
```

## Register source input

Local repository:

```bash
curl -sS -X POST http://localhost:8000/api/v1/repositories/discover \
  -H 'Content-Type: application/json' \
  -d '{"roots":["/path/to/repository"]}'
```

Bitbucket repository:

```bash
curl -sS -X POST http://localhost:8000/api/v1/repositories/discover \
  -H 'Content-Type: application/json' \
  -d '{"remotes":[{"location":"https://stash.example/scm/project/repository.git"}],"defer_checkout":true}'
```

## Inspect Knowledge Profiles

```bash
curl -sS http://localhost:8000/api/v1/knowledge-profiles
curl -sS http://localhost:8000/api/v1/knowledge-profiles/data-model-v1
```

## Preview a job

```bash
curl -sS -X POST http://localhost:8000/api/v1/jobs/preview \
  -H 'Content-Type: application/json' \
  -d @job.json
```

Previewing compiles commands and paths but does not create a job or execute tools. Secret values are rejected or redacted.

## Run data-model knowledge execution

`job.json`:

```json
{
  "kind": "knowledge_execution",
  "display_name": "Client Profile data model",
  "target": {
    "repository_id": "client-profile",
    "system_id": "client-profile"
  },
  "scenario_id": "build-data-model-v1",
  "build_report": true,
  "audience": "architecture",
  "detail_level": "detailed",
  "focus": ["Customer"],
  "parameters": {
    "model": "DeepSeek-v4-pro",
    "duckdb_memory_limit": "1GB",
    "duckdb_threads": 1
  },
  "output": {
    "replace": false
  }
}
```

Run:

```bash
curl -sS -X POST http://localhost:8000/api/v1/jobs \
  -H 'Content-Type: application/json' \
  -d @job.json
```

Knowledge composition is fixed by the referenced reusable Knowledge Profile. Scenarios that require a physical model, such as `extend-data-model-attribute-v1`, require a readable `.pdm` path through their context parameters.

## Observe execution

```bash
curl -sS http://localhost:8000/api/v1/jobs/<job-id>
curl -sS "http://localhost:8000/api/v1/jobs/<job-id>/logs?cursor=0"
curl -N "http://localhost:8000/api/v1/jobs/<job-id>/events?after=0"
curl -sS http://localhost:8000/api/v1/jobs/<job-id>/artifacts
```

Artifacts are registered as soon as their producing stage succeeds and remain visible if a later stage fails.

## Open the published revision

The successful job contains `system_id`, final `revision_id` and optional report artifacts. Knowledge is read through:

```text
/api/knowledge/v1/systems/<system-id>/revisions/<revision-id>
/api/knowledge/v1/systems/<system-id>/knowledge-artifacts?revision_id=<revision-id>
/api/knowledge/v1/systems/<system-id>/capabilities?revision_id=<revision-id>
```

## Consume the published revision

Chat/LLM consumption is intentionally outside Knowledge Control Plane. A consumer uses the exact `system_id`/`revision_id` through Knowledge API and the framework-owned `knowledge-integration` contract.

## Cancel, retry and diagnostics

```bash
curl -sS -X POST http://localhost:8000/api/v1/jobs/<job-id>/cancel
curl -sS -X POST http://localhost:8000/api/v1/jobs/<job-id>/retry \
  -H 'Content-Type: application/json' \
  -d '{"from_stage":"publication"}'
curl -sS http://localhost:8000/api/v1/jobs/<job-id>/commands
curl -sS -X POST http://localhost:8000/api/v1/jobs/<job-id>/diagnostics-bundle \
  -H 'Content-Type: application/json' \
  -d '{"max_log_entries":100000}'
```

Retry creates a new job and may reuse only artifacts explicitly supported by the current knowledge-execution stages. It never invokes the removed Task/Suite/Profile product route.

## Runtime database

Use a new SQLite database for 2.0.0a65. Older runtime schemas are rejected intentionally and are not migrated.
