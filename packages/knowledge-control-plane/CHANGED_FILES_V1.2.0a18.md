# Knowledge Control Plane 1.2.0a18 — Generator/Chat split Block A

## Purpose
Break the active Knowledge Control Plane product at the published Knowledge API revision boundary. Knowledge Control Plane is now the Knowledge Base Generator runtime; chat/LLM dialogue is no longer hosted by this package.

## Runtime changes
- removed `knowledge-assistant` package dependency;
- removed Assistant execution/context services and `/api/v1/assistant-contexts/**` routes;
- removed Assistant context/message/trace tables from newly created runtime databases;
- removed `assistant_ready` production stage and `assistant_context_id` from job result contract;
- production now finishes after publication and optional report build;
- removed embedded Chat frontend route, view and components;
- revision/result views end at the published Knowledge API revision;
- public orchestration OpenAPI no longer advertises assistant contexts;
- retained scenario `assistant_profile_id` as consumer-guidance metadata only; it does not activate an Assistant runtime.

## Validation
- generator/chat boundary + OpenAPI/frontend targeted tests: 20 passed;
- selected production pipeline stage tests: 2 passed;
- Python compileall: PASS;
- import with `knowledge-assistant` excluded from PYTHONPATH: PASS;
- frontend `npm ci && npm run build`: not completed; dependency installation exceeded the 120-second test limit and is not reported as PASS.

## Non-goals
- no Knowledge Chat project extraction yet (Block B);
- no Core, Runner, KLC, Knowledge API or knowledge-integration semantic changes;
- no full regression run.
