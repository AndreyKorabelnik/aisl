# Analysis UI 2.0.0a42

- Aligns FDP repository pipelines with canonical `analysis_suite_run_manifest/v1`.
- Uses the canonical Knowledge Layer already produced by workspace suite runs.
- Rejects workspace manifests as repository suite manifests instead of guessing.
- Emits `selected_repository_sources/v2` for workspace execution.
- Adds cross-component contract regression coverage for runner 0.9.28.
