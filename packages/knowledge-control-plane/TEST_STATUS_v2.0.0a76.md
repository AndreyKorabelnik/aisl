# Test status — Analysis UI 2.0.0a76

## Completed

- Backend compileall: passed.
- Prepared-revision Assistant runtime tests: 8 passed together with static revision-chat contracts.
- Knowledge/OpenAPI/Job targeted set: 32 passed.
- Full Python test suite: run after final packaging checkpoint.
- Generated OpenAPI contract refreshed and contract test passed.

## Environment limitation

Frontend dependency installation could not complete in this environment because the configured npm registry returned HTTP 404 for `vue-tsc@2.2.12`. Therefore frontend `vue-tsc`/Vite build is **not claimed as passed** in this checkpoint. Static frontend contract tests remain part of the Python suite.
