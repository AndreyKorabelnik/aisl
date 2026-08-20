# Test results — analysis-ui 2.0.0a29

- Python `compileall`: passed.
- Focused backend/frontend/API regression: 41 passed.
- Existing-job import contract: succeeded published job accepted; failed and unpublished jobs excluded/rejected; duplicate import rejected.
- No-republication invariant: passed in tests and in the real DuckDB smoke.
- Canonical OpenAPI regeneration: passed.
- Frontend orchestration/Knowledge API boundary, visual baseline, dependency portability and knowledge-boundary checks: passed.
- TypeScript and Vue `<script setup>` syntax transpilation using the installed TypeScript compiler: passed.
- Real smoke: an existing 97,792,000-byte datamart DuckDB was imported through a successful published job; 7 capabilities were read; analysis was not rerun, the file was not copied and publication was not called.
- `npm ci`, `vue-tsc` and Vite production build: not run because the runtime's internal npm proxy does not provide the required packages; this remains an environment limitation, not a passing build.
- Full project suite: not run; analyzers, job execution, Knowledge Layer materialization and existing system pages were not changed.
