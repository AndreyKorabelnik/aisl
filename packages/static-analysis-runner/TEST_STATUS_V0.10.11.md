# Test status — static-analysis-runner 0.10.11

- Targeted/contract tests in the final monorepo-like environment: **41 passed**.
- Covered evidence executor, knowledge execution, knowledge execution planning, knowledge materialization executor, and data-model discovery.
- Added a negative contract test proving a recomputed old result carrying removed `dual_write` is rejected.
- An earlier run without KLC on `PYTHONPATH` produced environment-only import failures; rerun with the packaged KLC passed completely.
- Compile/import smoke: passed.
- Full Runner regression was intentionally not run for this focused cut.
