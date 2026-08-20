# Analysis UI 2.0.0a74

## Summary

Keeps the human-facing `analysis-ui run` one-shot CLI and replaces the temporary Step41 runtime-contract snapshot with a bundle generated from the current framework contracts.

Current bundle baseline:

- code-analyzer-core 0.44.11;
- static-analysis-runner 0.10.6;
- knowledge-layer-core 0.59.16.

Normal runtime does not require any `validation/**` directory.

## Runtime contract validation

The packaged bundle now has `analysis_ui_runtime_contract_bundle/v2` metadata with:

- exact catalog schema versions;
- catalog fingerprints;
- SHA-256 for every bundled catalog;
- framework module versions.

Startup validates file checksums, manifest/catalog fingerprints and Knowledge-catalog links to the Core/KLC catalogs. Explicit `ANALYSIS_UI_*_CATALOG` overrides remain available for diagnostics.

## One-shot CLI

The existing `analysis-ui run` path is unchanged: it still uses the same `RuntimeContext` and `JobManager` as the REST/UI path and does not introduce a second execution implementation.
