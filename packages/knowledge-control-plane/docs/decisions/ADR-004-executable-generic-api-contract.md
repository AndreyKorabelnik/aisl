# ADR-004: executable generic API contract

## Status

Superseded by ADR-010 for `knowledge-control-plane 2.0.0a8`. Retained as historical context.


## Context

UI2 1.4.7 couples Vue components to legacy task-oriented routes and WebSocket messages. The replacement architecture needs generic orchestration capabilities while the existing `data-model-api` routes must remain unchanged.

A documentation-only endpoint list would allow runtime code, frontend clients and OpenAPI documentation to drift.

## Decision

The canonical generic API is defined by strict Pydantic public models and an isolated FastAPI contract router under:

```text
src/knowledge_control_plane/api/generic_v1
```

A deterministic OpenAPI document is generated and verified by tests. The contract router remains an isolated deterministic OpenAPI source whose handlers return HTTP 501. The executable implementation added in iteration 3 lives under `knowledge_control_plane.runtime` and is tested against the same operation set and public models. It is still not mounted into the legacy runtime.

The root health route and `/api/v1/systems/**` namespace remain owned by `data-model-api`. The generic API uses `/api/v1/version` and `/api/v1/capabilities` for its own diagnostics.

Live job updates use SSE rather than WebSocket. Artifact identifiers are registry IDs, never arbitrary filesystem paths.

## Consequences

- The iteration 3 runtime satisfies the contract operation and namespace tests.
- Frontend migration can generate or hand-write a typed client against one stable OpenAPI document.
- Data-model schemas are not duplicated in `knowledge-control-plane`.
- Legacy paths are migration inputs, not compatibility commitments.
