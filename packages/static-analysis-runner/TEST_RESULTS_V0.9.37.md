# Test results — static-analysis-runner 0.9.37

## Completed

- Mechanism catalog, CLI, built-in suite catalog and repository suite tests: **24 passed**.
- Knowledge Layer materialization, physical model and SQL repository contract tests with local DuckDB 1.5.5 wheel: **18 passed**.
- Profile resolution comparison against the canonical Code Analyzer Core 0.43.20 resolver: **14 profiles passed**.
- Real-source catalog generation:
  - Analysis UI pipeline profiles: 5;
  - Runner suites: 7;
  - Runner tasks: 8;
  - linked Core profiles: 8;
  - output fingerprint recorded in `validation/mechanism-catalog/analysis-mechanism-catalog.json`.

## Full-suite attempt

A complete Runner pytest invocation was attempted. The first attempt could not collect Knowledge Layer tests because `knowledge_layer_core` was not on `PYTHONPATH`. The second attempt included KLC 0.53.7 but used an environment without DuckDB and therefore produced four dependency failures before the command reached the execution timeout. The affected Knowledge Layer contract tests were then rerun with the provided DuckDB 1.5.5 wheel and passed: **18 passed**.

The complete unchanged Runner regression was not rerun to completion because this iteration adds a read-only catalog/CLI and does not alter repository, workspace, suite execution or materialization paths.

## Packaging

- `compileall`: passed.
- Wheel built offline with `--no-build-isolation`: passed.
- Wheel smoke from a neutral directory: version `0.9.37`, real-source catalog generated with 7 suites and 8 tasks.
