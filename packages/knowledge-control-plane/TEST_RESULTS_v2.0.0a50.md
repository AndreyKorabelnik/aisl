# Test results — Analysis UI 2.0.0a50

## Scope

Only the tests affected by SQL Knowledge Layer publication, human-readable job/revision names, report LLM configuration, publication retries, API contracts and frontend boundaries were run.

## Results

- Backend/API/frontend contract group: **42 passed**.
  - generic API contract;
  - module baseline;
  - runtime store lifecycle;
  - analysis artifact registry;
  - revision-first UI;
  - frontend generic migration.
- SQL/report execution group: **5 passed**.
  - SQL repository routing;
  - reuse and publication of repository-created SQL Knowledge Layer;
  - stable logical repository IDs;
  - `LLM_BASE_URL` compatibility for `knowledge-reporting`;
  - saved default model, endpoint and mTLS propagation for a workspace report.
- Publication and retry group: **5 passed**.
  - canonical Knowledge API publication;
  - preservation of artifacts after publication failure;
  - retry from publication without repeating analysis/report;
  - versioned system/report publication;
  - revision recreation from reused artifacts.

Total independently completed affected checks: **52 passed**.

## Additional validation

- Python `compileall`: passed.
- Frontend orchestration/API boundary: passed.
- Frontend dependency portability: passed.
- Frontend visual contract: passed.
- Knowledge API boundary inventory: passed.
- OpenAPI contract verification: passed.
- Source manifest generation and verification: passed.

## Not run

The full historical regression suite was not run because the user requested only necessary testing and the product changes are localized.

The production frontend build was not run in the packaging environment because `frontend/node_modules` is not distributed. No frontend dependencies were added; run `npm ci --include=dev && npm run build` in the target environment.
