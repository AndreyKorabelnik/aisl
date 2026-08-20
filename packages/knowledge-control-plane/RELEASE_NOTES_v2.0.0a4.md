# analysis-ui 2.0.0a4

Iteration 4 connects the existing Vue UI to generic API v1 without changing its visible templates or CSS.

## Added

- strict TypeScript contracts for jobs, repositories, profiles, logs, events, artifacts, conversations and preserved data-model routes;
- one typed Axios client for all HTTP access;
- SSE job subscriptions with durable cursors and polling fallback;
- generic job-to-legacy-view mapping so the existing components keep their visual behavior;
- report lookup, preview and download through the Artifact Registry;
- capability-aware assistant visibility;
- production serving of a built `frontend/dist` at `/` and `/analysis/{job_id}`;
- visual baseline manifest and verification for all Vue templates/styles;
- frontend generic API contract tests and ADR-006.

## Removed from frontend

- `/api/analyze`;
- `/api/task/{task_id}` and `/api/tasks`;
- `/api/report/{task_id}`;
- `/api/ask` and `/api/ask/{task_id}/history`;
- WebSocket `/ws/{task_id}`;
- direct Axios imports from Vue components.

## Preserved

- all 20 Vue template/style sections are byte-identical to UI2 1.4.7;
- generic backend remains outside `/health` and `/api/v1/systems/**`;
- typed client retains all six data-model API entry points.

## Capability gates

- remote Bitbucket checkout;
- multi-stage `full_pipeline` execution;
- generic assistant execution.
