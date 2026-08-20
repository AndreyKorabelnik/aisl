# Test Results — knowledge-layer-core 0.55.0

## Targeted checks

- 40 passed: logical/physical mapping, generic materialization runtime, contracts, physical model, code-declared model, offline version and manifest validation.
- `compileall`: passed.

## Expanded regression

A single long-lived pytest process exceeded the environment limit without reporting a test failure. The complete suite was therefore executed in isolated batches and, for the order-sensitive workspace file, in two test groups.

Result across every collected KLC test:

- **233 passed**;
- **13 skipped** existing optional/offline scenarios;
- **0 failed**.

No Core, API, Reporting, Assistant or UI regression was run because those modules are unchanged in this KLC iteration.

## Real second-family smoke

Executed with Core 0.43.28, Runner 0.9.51 and KLC 0.55.0:

- Core analyzers: 2;
- typed evidence artifacts: Java type structure, Java persistence mapping and external physical model;
- KLC materializations: `code-declared-data-model`, `physical-model`, `logical-physical-mapping`;
- entity/table mappings: 2 matched;
- field/column mappings: 4 matched and 1 transient/not-applicable;
- key mappings: 2 matched;
- relationship mappings: 1 matched;
- mapping gaps: 0.
