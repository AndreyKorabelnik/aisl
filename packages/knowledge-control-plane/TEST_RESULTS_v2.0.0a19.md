# Test results — analysis-ui 2.0.0a19

- Base/backend/contract tests: **38 passed**.
- Runtime tests: **50 passed** in stable groups.
- Workspace selection manifest regression: PASS.
- Event-loop responsiveness regression: PASS.
- Accepted-job frontend contract: PASS.
- Compilation and OpenAPI generation: PASS.

A single long TestClient process can still stall during teardown in the constrained recovery environment; no assertions failed and all runtime scenarios passed in grouped runs.
