# analysis-ui 2.0.0a12 — frontend uses public Knowledge API

## Scope

The Vue frontend now treats published knowledge as an external platform domain.

- `services/api.ts` remains the Analysis UI orchestration client.
- `services/knowledge-api.ts` is the canonical Knowledge API client.
- `services/knowledge-types.ts` mirrors the producer-neutral `/api/knowledge/v1` response models.
- system catalog, revision history, tables, table detail and published reports no longer use transitional `/api/v1/systems/**` routes.
- completed jobs navigate using `JobDetails.publication.system_id`, with target fallback only for older jobs.

## Development routing

Vite sends `/api/knowledge/**` to Knowledge API on port 8080 and other `/api/**` requests to Analysis UI on port 8000.
Production same-origin proxy support remains scheduled for iteration 16.

## Compatibility

Transitional local knowledge routes still exist in the Analysis UI backend until iteration 17, but the frontend no longer consumes them.
