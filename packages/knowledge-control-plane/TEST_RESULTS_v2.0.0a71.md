# Test results — Analysis UI 2.0.0a71

## Scope

Regression fix for standalone `analysis-ui run` Knowledge contract discovery.

## Results

- Targeted discovery + one-shot CLI tests: 21 passed.
- Full Analysis UI pytest suite: 66 passed.
- `python -m compileall -q src`: passed.
- Knowledge execution architecture audit: passed.
- Source manifest verification: passed after regeneration.
- Runtime contract discovery against step42 modules: passed.

Resolved catalogs in the step42 compatibility smoke:

- Core: `code-analyzer-core-0.44.6/validation/core-evidence-contract-catalog-v1.json`
- Knowledge: `static-analysis-runner-0.10.6/validation/runtime-contracts-v0.10.4/knowledge-catalog.json`
- Materialization: `knowledge-layer-core-0.59.6/validation/runtime-contracts-v0.59.1/knowledge-materialization-contracts.json`

The Knowledge catalog was verified to reference the exact discovered Core evidence and KLC materialization catalog fingerprints.

## Not repeated

A fresh real SQL repository E2E was not repeated for this patch because the changed code is limited to contract-path discovery; the execution path itself is unchanged. The step41 execution path remains the latest real E2E baseline.
