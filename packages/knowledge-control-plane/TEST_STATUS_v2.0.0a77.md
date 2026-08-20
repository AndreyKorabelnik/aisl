# Test status — Analysis UI 2.0.0a77

## Passed

- Architecture audit: PASS.
- Python compileall (`src`): PASS.
- Source manifest verification: PASS.
- Frontend orchestration/Knowledge API boundary contract: PASS.
- Frontend dependency portability check: PASS (310 packages use public HTTPS registry URLs; no private credentials/host in `.npmrc`).
- Full Python test suite: **78 passed**.
- OpenAPI contract: regenerated and covered by the full suite.
- Runtime contract bundle: regenerated from Core 0.44.16 / Runner 0.10.9 / KLC 0.59.36 and covered by contract tests.

## Consumer architecture acceptance relevant to this UI release

An isolated consumer-only runtime containing Evidence Common + KLC + Knowledge API + Knowledge Assistant, but **without Core, Runner or Analysis UI**, passed for two different knowledge products. The UI is therefore not a consumer-runtime dependency; it is an optional production/context-selection surface.

## Environment limitation

Frontend dependency installation / production build is **not claimed as passed**. The configured npm registry returned HTTP 404 for `vue-tsc@2.2.12`; `node_modules` was not created. Static frontend contracts and dependency-portability checks are green, but this does not replace a real `vue-tsc`/Vite build when the registry artifact becomes available.
