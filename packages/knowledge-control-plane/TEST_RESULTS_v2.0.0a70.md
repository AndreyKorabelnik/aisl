# Analysis UI 2.0.0a70 test results

## Automated checks

- Full Analysis UI regression: **65 passed**.
- New one-shot CLI + affected orchestration/API target set: **25 passed**.
- Python `compileall` for `src` and `tests`: **OK**.
- `analysis-ui run --help`: **OK**; terminal command is available without starting `analysis-ui serve`.
- Knowledge Profile registry inspection: **5 current profiles** loaded from `analysis_ui.runtime.profiles.ProfileService`.
- Frontend orchestration / Knowledge API boundary verifier: **passed**.
- Frontend dependency portability: **passed** (310 public HTTPS registry packages).
- Knowledge execution architecture audit: **passed** for 2.0.0a70.
- Source manifest: **346 files, OK** after final regeneration.

## Scope

This iteration changes only Analysis UI. Core, Runner, KLC, Knowledge API, Reporting and Assistant code are unchanged from step41.

The new CLI was validated at the orchestration/unit boundary and through the complete Analysis UI regression suite. A fresh real application E2E was not repeated for this thin control-plane adapter; actual analysis execution remains the same `JobManager` path already exercised by the step41 real E2E.

A fresh local real SQL-datamart E2E was also not attempted because the current tool environment does not have the required offline runtime wheels installed (`tree_sitter`, `tree_sitter_java`, `sqlglot`, `duckdb`). This is an environment limitation, not a failed test.

Knowledge API remains an external runtime dependency for revision publication; `analysis-ui serve` is not required for `analysis-ui run`.
