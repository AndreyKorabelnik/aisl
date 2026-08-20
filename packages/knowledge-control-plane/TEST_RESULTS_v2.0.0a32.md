# Test results — analysis-ui 2.0.0a32

- Focused Python/API/frontend contract tests: 38 passed.
- Existing workspace full-pipeline regression: 1 passed.
- Total focused pytest checks: 39 passed.
- New `knowledge-context-pipeline:v1` runtime smoke: succeeded; static analysis, Knowledge Layer and publication succeeded, report stage skipped.
- Python `compileall`: passed.
- Frontend orchestration/knowledge-boundary, visual-baseline and dependency-portability checks: passed.
- TypeScript/Vue script syntax transpilation: 24 files passed.
- Canonical OpenAPI and source manifest: passed.
- ZIP integrity: pending clean-package verification.
- `npm ci --offline` / Vite build: not run successfully because the local npm cache does not contain `vue-tsc-2.2.12`; no network fallback was used.
- Full project suite: not run. Analyzer execution, Knowledge Layer materialization internals and job scheduling were not changed; one new pipeline smoke and the existing workspace-pipeline regression cover the affected orchestration path.
