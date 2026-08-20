# Generator UI extraction acceptance

Date: 2026-08-14

## Passed

- Standalone Generator UI boundary tests: 4/4 PASS.
- Headless KCP focused backend regression before final docs cleanup: 56/56 PASS.
- Final headless boundary/API subset: 24/24 PASS.
- KCP compile/import: PASS.
- Headless runtime acceptance: `/` is no longer a frontend route; `/api/v1/capabilities` remains available.
- KCP source contains no `frontend/`, `StaticFiles`, `frontend_dist` or `KNOWLEDGE_CONTROL_PLANE_FRONTEND_DIST`.

## Not reported as PASS

Frontend production build was not completed in this environment. Offline npm cache lacks `vue-tsc@2.2.12`; a registry-backed install was not reliably available. No build PASS is claimed.

## Full regression

Not run. The change is a packaging/UI ownership split; Core/Runner/KLC semantics were untouched. Targeted backend and boundary tests were used instead.
