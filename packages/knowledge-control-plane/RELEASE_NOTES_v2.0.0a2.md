# analysis-ui 2.0.0a2

Iteration 2 establishes the canonical generic orchestration API contract while preserving the UI2 1.4.7 runtime unchanged.

## Added

- strict Pydantic request and response models for generic API v1;
- executable FastAPI contract router;
- deterministic OpenAPI document;
- repositories, workspaces, profiles, jobs, logs, SSE events, artifacts and assistant conversations;
- exact legacy-route migration map;
- explicit preserved data-model endpoint manifest;
- contract tests for paths, methods, schemas, media types and namespace isolation.

## Not implemented yet

Contract handlers intentionally return HTTP 501. Runtime services and persistence are iteration 3 work.
