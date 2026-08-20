# Test results — static-analysis-runner 0.9.39

## Result

All **96** packaged Runner tests passed in four bounded groups with Knowledge Layer Core 0.53.7 and DuckDB 1.5.5 available on `PYTHONPATH`.

- Core Runner / catalog / suite / materialization group: **55 passed**
- SQL repository group: **14 passed**
- Portfolio topology group: **11 passed**
- Workspace group: **16 passed**
- Total: **96 passed**

Additional checks:

- Core profile resolver comparison: **14 profiles matched** the canonical `code_analyzer_core.analysis_profiles` resolver.
- Current Core stage taxonomy: **48/48 stage IDs classified**, no unclassified IDs.
- Java derived-evidence contracts: **9/9 declared runtime stages covered**.
- Suite reuse assessment: **4 ready, 4 conditional, 1 blocked**.
- `compileall`: passed.

## Runtime behavior

This iteration is read-only. It does not change Suite, Task, Core Profile, Foundation, stage order, Knowledge Layer materialization or output contracts.
