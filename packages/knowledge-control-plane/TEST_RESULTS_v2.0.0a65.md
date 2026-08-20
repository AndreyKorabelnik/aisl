# Test results — Analysis UI 2.0.0a65

## Source tree

- Full current Analysis UI test suite: **53 passed, 0 failed**.
- `python -m compileall src tests scripts`: passed.
- Generated OpenAPI contract: passed.
- Knowledge-execution architecture audit: passed.

## Fresh canonical UI route

Input: local Java repository plus PowerDesigner PDM.

Result:

- all 8 visible job stages succeeded;
- Core analyzer executions: 2;
- KLC materialization executions: 4;
- knowledge artifacts: 5;
- published capabilities: 17;
- Knowledge API publication: passed;
- report build from pinned revision: passed;
- deterministic Mermaid present in report: passed;
- immutable Assistant context: created;
- capability-gated `search_data_objects` tool call: passed.

Detailed machine-readable result: `validation/analysis-ui-2.0.0a65/full-route-smoke.json`.

## Frontend build

`npm ci --offline` is blocked because the offline cache does not contain `vue-tsc-2.2.12.tgz`. Vite/`vue-tsc` production build was therefore not claimed. The exact logs and exit codes are preserved under `validation/analysis-ui-2.0.0a65/`.

Static frontend routing, progress, migration, Mermaid and API-client regressions are included in the 53 passing tests.
