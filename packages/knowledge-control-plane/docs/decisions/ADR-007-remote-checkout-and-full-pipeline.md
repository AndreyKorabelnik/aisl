# ADR-007: Protected remote checkout and durable full pipeline

Status: Accepted in `2.0.0a5`.

## Context

The migrated UI can create generic jobs, but a Bitbucket URL was previously only registered. The UI therefore could not execute its original end-to-end scenario. Reporting also had to be launched as a separate job, which hid the relationship between static analysis, Knowledge Layer materialization and the final report.

## Decision

A `full_pipeline` job is one durable job with four explicit stages:

```text
checkout -> static_analysis -> knowledge_materialization -> report_build
```

Remote repositories are materialized under the Knowledge Control Plane runtime root. The public repository record keeps the original remote URL; the local checkout path is stored only as runtime metadata.

Authentication uses `GIT_ASKPASS`. Tokens may be supplied for immediate discovery checkout or through protected environment variables, but are never written to SQLite or command payloads.

Every stage registers its artifacts immediately with a stage prefix. Failure of a later stage does not invalidate earlier results. Retry can reuse a manifest or Knowledge Layer artifact from the previous job.

## Consequences

- the UI can launch a Bitbucket URL through one generic job;
- checkout, analysis, Knowledge Layer and report progress are independently observable;
- report retry does not repeat static analysis;
- remote source trees remain outside output directories;
- Git becomes an explicit runtime prerequisite for remote checkout;
- generic assistant execution remains a separate future capability.
