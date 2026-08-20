# Test status — code-analyzer-core 0.43.28

Full Core regression was intentionally not run because the change is isolated to one new prepared artifact, its registry entry and evidence contracts.

## Targeted checks

- Persistence mapping evidence builder/runtime tests.
- Existing Java type-structure evidence tests.
- Core evidence contract catalog tests.
- Strict public-contract test.

Result: **19 passed**.

## Additional validation

- `compileall`: passed.
- Generic Core runtime smoke with two analyzers: passed.
- Published evidence artifacts: 2.
- Persistence smoke: 2 type mappings, 4 field mappings, 2 key mappings, 1 relationship mapping, 0 diagnostics.
- Contract catalog: 2 runtime-published evidence families.
- Hidden fallback / dual-write: not supported.
