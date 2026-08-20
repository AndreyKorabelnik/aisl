# Knowledge Base Generator UI extraction

Date: 2026-08-14
Status: COMPLETE

## Architecture change

The remaining production frontend has been extracted from `knowledge-control-plane` into the standalone `knowledge-base-generator-ui` project.

Framework canonical boundary:

```text
Sources -> headless Knowledge Control Plane -> Core/Runner/KLC -> Knowledge API revision
```

UI boundary:

```text
Knowledge Base Generator UI -> KCP HTTP API + Knowledge API
Knowledge Chat UI          -> separate consumer/agent backend + Knowledge API
```

## Framework changes

- `knowledge-control-plane 1.2.0a19 -> 1.2.0a20`.
- Removed `frontend/` from KCP.
- Removed static frontend serving and `frontend_dist` runtime configuration.
- Removed `KNOWLEDGE_CONTROL_PLANE_FRONTEND_DIST`.
- Removed frontend-build diagnostics and UI-owned validation scripts from KCP.
- KCP remains owner of orchestration APIs and optional transparent Knowledge API reverse proxy.
- No Core, Runner, KLC, Knowledge API or knowledge-integration runtime semantics changed.

## Standalone UI

- New project `knowledge-base-generator-ui 0.1.0`.
- Own package metadata, README, deployment docs and boundary tests.
- Configurable KCP and Knowledge API HTTP boundaries.
- No Chat/Assistant runtime.
- No Python/framework runtime dependency.
