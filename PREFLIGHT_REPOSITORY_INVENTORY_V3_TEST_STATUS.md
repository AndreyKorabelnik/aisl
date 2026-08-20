# Repository Inventory v3 — Block C Test Status

Date: 2026-08-16
Status: PASS

## Full / broad regression

- code-analyzer-core: 609 passed.
- static-analysis-runner: 108 passed.
- knowledge-layer-core: 252 passed, 8 skipped.
- prepared-knowledge-runtime: 10 passed.
- knowledge-api: 118 passed.
- knowledge-control-plane: 95 passed.

## Targeted Block C checks

- KLC Repository Inventory v3 targeted: 14/14 PASS.
- Pre-checkpoint API/Portfolio/OpenAPI targeted: 15/15 PASS.
- Preserved dead-chat v2 → v3 concept parity: 12/12 exact rows.
- Fresh post-recovery gateway source rerun + Knowledge API publication: PASS.
- Fresh post-recovery SQL-heavy datamart source rerun + Knowledge API publication: PASS.
- Fresh rerun vs preserved v3 acceptance: 12/12 concept rows exact and all acceptance counts exact.
- Real bounded evaluation phase: 2/2 `preflight`.
- Deep official evidence fixture: `post_analysis` PASS.

## Test-run diagnostics

Two broad suites initially exceeded the execution-tool wall timeout after displaying no failures. They were rerun in deterministic file groups and only the completed grouped summaries above are counted as PASS. Timeout-only runs are not counted as functional failures or passes.

A Core run from the repository top-level produced two path-relative fixture failures; rerunning from the package root (the suite's expected working directory) produced 609/609 PASS. The top-level cwd failures are not treated as framework regressions.
