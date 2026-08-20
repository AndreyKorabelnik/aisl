# Test results — static-analysis-runner 0.9.38

## Result

All 95 packaged Runner tests passed when executed in four bounded groups with Knowledge Layer Core 0.53.7 and DuckDB 1.5.5 available on `PYTHONPATH`.

- Core Runner / catalog / suite / materialization group: **54 passed**
- SQL repository group: **14 passed**
- Portfolio topology group: **11 passed**
- Workspace group: **16 passed**
- Total: **95 passed**

Additional checks:

- Core profile resolver comparison: **14 profiles matched** the canonical `code_analyzer_core.analysis_profiles` resolver.
- Current Core stage taxonomy: **48/48 stage IDs classified**, no unclassified IDs.
- `compileall`: passed.

## Execution note

A single monolithic pytest invocation reached 75% without failures but exceeded the command execution limit. The same 95 collected tests were then run in four bounded groups and all completed successfully. The monolithic timeout is not reported as a passed run.

## Runtime behavior

The iteration is read-only. No analysis execution, Suite, Task, Core profile, Foundation, Knowledge Layer or artifact contract behavior changed.
