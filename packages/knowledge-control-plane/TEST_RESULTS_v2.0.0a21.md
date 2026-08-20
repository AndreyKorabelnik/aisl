# Test results — analysis-ui 2.0.0a21

- Python source/runtime compilation: PASS.
- Source manifest verification: PASS.
- Frontend visual contract: PASS (12 preserved sections, 14 workspace sections).
- Frontend orchestration/Knowledge API boundary: PASS.
- Frontend dependency portability: PASS.
- Knowledge ownership boundary audit: PASS.
- Frontend legacy naming audit: PASS; no `LegacyTaskView`, `LegacyTaskStatus`, `task_id`, task-based route props or old task client/store methods in production frontend sources.
- Base/backend-independent/contract tests: 38 passed.
- Supported runtime tests: 50 passed. A combined pytest process stalled during interpreter teardown after successful assertions; every runtime test was therefore confirmed in isolated processes and the stalled process was not counted as PASS.
- Frontend production build: not rerun in this offline checkpoint because `frontend/node_modules` is not included; dependencies and lockfile were unchanged.
