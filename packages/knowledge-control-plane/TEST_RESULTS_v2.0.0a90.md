# Test results — analysis-ui 2.0.0a90

- Full Python/contract/static frontend suite: **81 passed**.
- `scripts/verify_knowledge_execution_architecture.py`: **PASS**.
- Python `compileall`: **PASS**.
- Pinned runtime catalogs regenerated from canonical owner builders:
  - code-analyzer-core 0.44.20
  - static-analysis-runner 0.10.17
  - knowledge-layer-core 0.59.49
- Runtime contract bundle fingerprint/SHA tests: included in full suite and **PASS**.
- OpenAPI snapshot: regenerated after version/model changes and **PASS**.
- Frontend production build: **NOT RUN / NOT PASS**. `npm ci --offline` failed because `vue-tsc-2.2.12` was not present in the local npm cache; no network installation was attempted.
