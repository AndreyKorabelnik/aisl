# ADR-0012: Canonical producer-neutral Knowledge API contract

## Status

Implemented and cleaned up in `knowledge-api 0.5.0`.

## Context

`analysis-ui` previously duplicated system, revision, data-model and report semantics already belonging to `knowledge-api`. External consumers also require this information, so UI-owned or registry-owned semantic surfaces would create competing public contracts.

## Decision

`knowledge-api` owns all published knowledge through `/api/knowledge/v1`.

The API models stable systems and immutable revisions. A revision references a content-addressed Knowledge Layer artifact and an optional prepared report. Provenance uses generic producer and execution identifiers; it does not depend on `analysis-ui` jobs.

`analysis-ui` owns repositories, workspaces, jobs, stages, logs, artifacts, reuse and diagnostics. It publishes through the revision endpoint and proxies the same canonical API for browser traffic.

The registry-based read-only runtime and compatibility routes were removed. Backward compatibility is intentionally not retained.

## Consequences

- UI and external consumers share one knowledge contract.
- Knowledge semantics remain implemented once over `knowledge-layer-core`.
- Publication failures can be retried independently of analysis and reporting.
- The service exposes one OpenAPI document and one public route prefix.
- Internal KLC query adaptation is not a second public API.
