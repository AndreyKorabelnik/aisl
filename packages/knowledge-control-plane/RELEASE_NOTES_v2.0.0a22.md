# analysis-ui 2.0.0a22

## Iteration 25.2

- resolves `analysis-profiles` from an explicit override, an installed/editable `code-analyzer-core`, or supported project/archive layouts;
- keeps the explicit `ANALYSIS_UI_PROFILES_ROOT` authoritative even when the path is currently missing;
- falls back to one canonical diagnostic path when no profiles directory can be discovered;
- changes no orchestration, workspace, publication or frontend behavior.
