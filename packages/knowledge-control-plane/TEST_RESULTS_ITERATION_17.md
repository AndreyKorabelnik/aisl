# Test results — Iteration 17

Date: 2026-07-29
Artifact: `analysis-ui 2.0.0a14`

## Static and contract verification

- `python -m compileall`: PASS
- immutable baseline verification: PASS
- frontend visual contract: PASS
- frontend orchestration/Knowledge API boundary verification: PASS
- knowledge-domain ownership inventory: PASS
- generated OpenAPI contains no local `/api/v1/systems/**`: PASS

## Pytest

- backend, module, generic contract, frontend migration, proxy, publication and boundary tests: **85 passed**
- runtime/backend tests: **44/44 passed**
- total: **129 passed**

Runtime tests were executed in isolated/subset processes because a single-process run intermittently stalls during `TestClient`/subprocess teardown in the constrained recovery container. All 44 test cases completed successfully when isolated; no failed assertion remains.

## Specifically covered

- HTTP publication to `knowledge-api`;
- retry from the `publication` stage;
- stage cache and forced rebuild behavior;
- deletion protection for published jobs;
- migration cleanup of legacy `systems` and `system_revisions` SQLite tables;
- absence of local systems/data-model/report routes;
- frontend serving without intercepting orchestration routes;
- transparent same-origin `/api/knowledge/v1/**` proxy;
- diagnostics and error propagation.

No dependency was built from source.
