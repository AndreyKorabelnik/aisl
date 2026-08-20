# Test results — static-analysis-runner 0.9.48

## Final checks

- `compileall`: passed.
- Non-workspace Runner regression: **123 passed in 29.22s**.
- Workspace regression: **16/16 passed when executed as isolated test processes**.
- Total current Runner tests: **139 passed**.
- Generic release contract/source validation: passed.
- Architecture audit for `code-declared-data-model`: `target_ready`, 0 blocked gates.
- Real Runner → Core → KLC end-to-end smoke: passed.

The grouped workspace test process repeatedly stalled after the first test in this execution environment; every collected workspace test passed independently. This is recorded as a test-runner/process-order observation, not as a functional failure.

## End-to-end result

- Core: 0.43.27.
- Runner: 0.9.48.
- KLC: 0.54.1.
- Evidence artifacts: 1.
- Knowledge artifacts: 1.
- Published capabilities: 5.
- Legacy conceptual-model input consumed: no.
- Legacy fallback and dual-write: unsupported.

Logs and artifacts are under `validation/generic-evidence-executor-v0.9.48/`.
