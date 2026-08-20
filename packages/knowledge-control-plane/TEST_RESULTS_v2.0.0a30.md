# Test results — analysis-ui 2.0.0a30

- Python `compileall`: passed.
- Focused pipeline/retry/cache regression: 6 passed.
- Release/module baseline checks: passed.
- Prepared-context pipeline: static analysis, Knowledge Layer and publication succeeded; report stage skipped; no report artifact created.
- Later ordinary pipeline: static analysis and Knowledge Layer reused; report built successfully.
- A broader selected pipeline run reached the execution-time limit after multiple successful tests and is not counted as a completed run.
- Full project suite: not run; this focused pipeline contour was sufficient and avoids unnecessary test time.
