# ADR-008: Operational diagnostics are metadata-only by default

Status: Accepted in `2.0.0a6`.

## Context

Support engineers need reproducible commands, searchable logs, environment validation and a portable incident bundle. Copying complete output directories is unsafe because they may contain source code, Knowledge Layers, evidence, report datasets, credentials or private TLS material.

## Decision

`knowledge-control-plane` exposes a dedicated `DiagnosticsService` and five generic API operations:

```text
GET  /api/v1/diagnostics
GET  /api/v1/jobs/{job_id}/commands
GET  /api/v1/jobs/{job_id}/compare/{other_job_id}
GET  /api/v1/jobs/{job_id}/logs/download
POST /api/v1/jobs/{job_id}/diagnostics-bundle
```

The bundle includes only:

- application/platform metadata;
- sanitized public configuration status;
- typed job metadata and stage state;
- already-redacted command lines and logs;
- artifact metadata, names, sizes and hashes.

It does not include artifact contents, repository contents, DuckDB files, reports, TLS keys, tokens or environment values.

## Consequences

- support bundles are small and safe to transfer through ordinary support channels;
- artifact payloads must be requested explicitly and separately when genuinely required;
- `knowledge-control-plane doctor` can be used in deployment scripts before starting the service;
- reproducible command output is diagnostic guidance, not a generic shell-execution facility.
