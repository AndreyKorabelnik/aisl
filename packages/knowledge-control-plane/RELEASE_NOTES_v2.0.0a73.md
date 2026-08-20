# Analysis UI 2.0.0a73

## Summary

This release keeps Core, Runner and KLC unchanged and removes the Analysis UI runtime dependency on their project `validation/` directories.

Analysis UI now ships a compact, internally versioned runtime-contract bundle as normal package data. The bundle contains the compatible Core evidence catalog, KLC materialization catalog and Runner Knowledge catalog required by the current framework baseline.

The previously added `analysis-ui run` terminal entry point remains the high-level one-shot interface for manual execution of a Knowledge Profile without starting `analysis-ui serve`.

## Runtime contract packaging

Bundled resources:

- `analysis_ui/resources/runtime_contracts/core-evidence-contract-catalog.json`
- `analysis_ui/resources/runtime_contracts/knowledge-materialization-catalog.json`
- `analysis_ui/resources/runtime_contracts/knowledge-catalog.json`
- `analysis_ui/resources/runtime_contracts/bundle-manifest.json`

Baseline represented by the bundle:

- code-analyzer-core module: 0.44.6
- knowledge-layer-core module: 0.59.6; materialization catalog reports KLC contract version 0.59.1
- static-analysis-runner module: 0.10.6; Knowledge catalog reports Runner contract version 0.10.4

Runtime discovery no longer scans source workspaces or `validation/**`. Optional `ANALYSIS_UI_*_CATALOG` environment overrides remain supported for diagnostics/advanced deployments.

## One-shot CLI

Example:

```bash
analysis-ui run \
  --profile sql-source-inventory-v1 \
  --repository /path/to/datamart \
  --system-id datamart-profile-fl
```

`analysis-ui serve` is not required. The command reuses the same Analysis UI runtime services and `JobManager`; it does not create a parallel execution path. Knowledge API remains required for canonical publication.

## Validation

- Analysis UI full regression: 67 passed.
- Targeted one-shot/runtime-contract tests: 24 passed.
- `compileall`: OK.
- architecture audit: OK.
- wheel build without network/build isolation: OK.
- wheel content check: runtime-contract bundle included.
- clean target installation: discovery resolves only packaged Analysis UI resources; no `validation/` path is used.
