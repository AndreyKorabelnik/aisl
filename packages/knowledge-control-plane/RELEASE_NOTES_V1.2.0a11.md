# Knowledge Control Plane 1.2.0a11

- Added built-in Knowledge Profile `effective-data-model-v1` selecting existing Runner knowledge `effective-data-model`.
- Added built-in Scenario `build-effective-data-model-v1` for source-backed workspaces with required physical-model input.
- No new analyzer, KLC materializer, cache, Runner path or API contract. Existing Runner dependency resolution expands the profile to `code-declared-data-model`, `physical-data-model`, `logical-physical-mapping`, and `effective-data-model`.
- One-shot CLI uses existing repeated `--repository` and `--physical-model` options.
