# Analysis UI 2.0.0a69 test results

## Automated checks

- Full backend/static frontend regression: 60 passed.
- Targeted version/profile/OpenAPI checks: 11 passed.
- Python compileall: OK.
- Source manifest: 357 files, OK.
- Frontend orchestration/Knowledge API boundary verifier: passed.
- Frontend dependency portability: 310 public HTTPS registry packages, passed.
- Knowledge execution architecture audit: passed.
- Deterministic contract OpenAPI generation: passed; schema version `generic_api/v1`. Runtime OpenAPI reports application version 2.0.0a69.

## Real UI E2E

The UI runtime was created against the real local Knowledge API and active revision
`rev-c9c7a3315469cfe1814256f0` for system `ucp-datamart-pdm`.

Successful routes:

- capabilities;
- Knowledge API systems, revisions, artifacts and report proxy;
- revision-pinned assistant context creation;
- assistant question;
- conversation and assistant logs;
- OpenAPI.

All routes returned HTTP 200, except context creation which correctly returned HTTP 201.
The model system prompt contained the complete `attribute-addition-plan/v1` profile version 4
and the capability-gated tool catalog. The question used two real Knowledge API tools and
returned the observed `bplace.bp_value AS birth_place` projection and temporal JOIN while
leaving a separate birth-region-name field unresolved.

The UI E2E used a deterministic scripted model over the real UI and Knowledge API routes.
A hosted external LLM endpoint was not exercised.

## Frontend production build

Not executed: `frontend/node_modules` is absent and the npm cache is empty. Network dependency
installation was not attempted. Static typed-client, route-boundary and dependency-portability
checks passed and the missing production build does not block the backend E2E result.
