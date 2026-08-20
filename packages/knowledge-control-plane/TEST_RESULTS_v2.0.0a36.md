# Test results 2.0.0a36

- Collected Analysis UI backend tests: 121.
- Isolated execution result: **121 passed, 0 failed**.
  - 67 non-runtime tests executed module by module.
  - 54 `test_runtime_backend.py` tests executed in six isolated groups of 9; every group returned `rc=0`.
- A single-process full-suite run was not counted as successful: in this container it reached roughly 60% and then hung during `TestClient` teardown without a failed assertion. Isolated execution avoids this harness-level teardown issue and covers every collected node ID.
- Focused profile/context and target-handoff regression: passed.
- `compileall src/analysis_ui`: passed.
- Generated OpenAPI updated to 2.0.0a36 and verified by the API contract tests.
- Real standard endpoint profile-v2 probe: 15,479 prompt characters; complete `attribute-addition-plan/v1` present; shortened UI rules absent.
- Profile diagnostics: content version `2`, SHA-256 `34a80aa26852964ebc245821a7d0fa03208a6833b9f6c574d3d3f50f113db2a0`, load status `loaded`.
- Five real-evidence standard-chat scenarios: **5/5 passed**, 37 Knowledge API tool calls.
- Evidence validation: **29/29 assertions passed**.
- Frontend source was not changed; npm/Vite production build was not run.
- Full platform ingestion/parser suite was not repeated because those components were unchanged; the complete real UCP → datamart → PDM → Knowledge API → Assistant → Analysis UI chain was reproduced before the patch.

Machine-readable result: `validation/iteration-111-test-results/analysis-ui-2.0.0a36-test-summary.json`.
