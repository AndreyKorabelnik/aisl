# Test results 2.0.0a46 — Advanced CLI preview

## Confirmed

- Python `compileall` for `src` and `tests`: passed.
- Focused API/UI/runtime preview regression: **25 passed**.
  - preview uses the same `JobCreateRequest` contract as job creation;
  - preview does not create a job;
  - workspace preview does not write `workspace-selection.json`;
  - remote pipeline preview includes the planned `git clone` command;
  - secret token values are absent from the response;
  - preview does not create `git-askpass.py`.
- Base module regression: **42 passed**.
- Expanded affected-runtime selection: **22 passed** and **9 pre-existing failures**.
  - The same 9 tests fail identically on the untouched 2.0.0a45 baseline.
  - They submit repository targets to pipelines that are now workspace-only and fail before the stages asserted by those stale tests.
- Generated OpenAPI contract is current and includes `POST /api/v1/jobs/preview`.
- Frontend orchestration/Knowledge API boundary check: passed.
- Frontend dependency portability: passed; 310 resolved packages use public HTTPS registry URLs.
- Frontend visual contract: passed; 12 preserved and 12 workspace sections verified.
- TypeScript/Vue syntax transpile: passed for 27 frontend files.

## Frontend production build

`npm ci` did not complete in the execution environment. The configured package gateway returned HTTP 404 for `vue-tsc-2.2.12.tgz`; therefore `vue-tsc` and Vite production build were not run. The failure is captured in `validation/cli-preview/npm-ci.log`.

## Scope not claimed

- A completely green full legacy runtime suite is not claimed because of the 9 confirmed baseline-stale pipeline tests described above.
- Browser-level visual interaction was not executed; template integration, API contract, visual hashes and TypeScript/Vue syntax were verified.
