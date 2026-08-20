# ADR-006: Migrate UI2 transport without changing visible UI

## Status

Superseded by ADR-010 for `knowledge-control-plane 2.0.0a8`. Retained as historical context.

## Decision

Keep the Vue templates and styles from UI2 1.4.7 unchanged, but replace all direct legacy HTTP and WebSocket calls with one typed generic API client.

Use SSE for durable job updates and polling only as a recovery fallback. Resolve reports through the Artifact Registry. Hide assistant controls when the capability is unavailable. Keep data-model endpoints outside the generic backend and expose typed client methods for them.

## Consequences

- the screen layout and visual styling remain stable;
- frontend components no longer know endpoint paths or Axios details;
- job state names are mapped at the client boundary (`succeeded` → `completed`);
- full report-producing Bitbucket workflows remain gated until full-pipeline orchestration and remote checkout are implemented;
- future changes to generic API models are localized to `services/types.ts` and `services/api.ts`.
