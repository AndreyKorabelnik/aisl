# Changed files — Analysis UI 2.0.0a65

## Added

- `scripts/verify_knowledge_execution_architecture.py`
- `validation/analysis-ui-2.0.0a65/*`
- `RELEASE_NOTES_v2.0.0a65.md`
- `TEST_RESULTS_v2.0.0a65.md`
- `HANDOVER_v2.0.0a65.md`

## Removed

- `src/analysis_ui/runtime/analysis_artifacts.py`
- `src/analysis_ui/runtime/cache.py`
- legacy Analysis Artifact, old Assistant context, profile-discovery and runtime-backend tests
- obsolete workspace visual-contract documents and legacy-boundary audit scripts

## Main modified areas

- API contract and models
- runtime jobs, pipeline, commands, store, configuration and output safety
- knowledge contract discovery and publication
- revision-pinned Assistant execution
- Knowledge Profile master, progress, revision result and chat frontend
- OpenAPI and current architecture/operations documentation
- package versions and current regression tests
