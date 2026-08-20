# Test results — analysis-ui 2.0.0a28

- Python `compileall`: passed.
- Focused backend/frontend contracts: 31 passed.
- Prepared-context wizard route, no-manual-target contract, standard Renderer chat and context API checks: passed.
- Production frontend fallback for `/assistant-contexts` and `/assistant-contexts/{context_id}`: passed.
- TypeScript and Vue `<script setup>` syntax transpilation using the installed TypeScript compiler: passed.
- Frontend orchestration/Knowledge API boundary, visual baselines and dependency portability: passed.
- Canonical OpenAPI regeneration: passed.
- `npm ci`, `vue-tsc` and Vite production build: not run because the configured internal npm proxy returned HTTP 404 for `vue-tsc` and `vite`; direct public-registry access is unavailable in this runtime. This is recorded as an environment limitation, not a passing build.
- Full project suite: not run; analyzers, jobs, Knowledge Layer materialization and existing system pages were not changed.
