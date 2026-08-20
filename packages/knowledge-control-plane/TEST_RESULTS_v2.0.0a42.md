# Test results 2.0.0a42 — canonical runner contracts

## Confirmed

- Real repository FDP suite with runner 0.9.28, core 0.43.18 and KLC 0.53.4: completed; `analysis_suite_run_manifest/v1`; capability `suite.fdp`.
- Real workspace FDP suite: completed; `static_workspace_analysis_run_manifest/v2`; shared `workspace/knowledge-layer.duckdb`; capability `suite.fdp`.
- Focused FDP/revision/UI tests: 14 passed.
- Runtime backend tests executed in isolated groups: 55 passed; one `doctor` test requires installed Knowledge Assistant in its subprocess environment and is not a product assertion failure.
- One workspace-cache test still hangs during the pytest process lifecycle and was not claimed as passed; the remaining runtime tests completed in isolated groups.
- Python compileall: passed.
- OpenAPI generation: passed.
- Frontend contract check: passed.
- TypeScript/Vue script syntax: passed.
- Source manifest and ZIP integrity: checked after packaging.

## Contract fixed

- Repository suite manifest is exactly `analysis_suite_run_manifest.json` with schema `analysis_suite_run_manifest/v1`.
- Workspace manifest is exactly `static_analysis_run_manifest.json` with schema `static_workspace_analysis_run_manifest/v2`.
- Workspace pipelines reuse the Knowledge Layer produced by the workspace runner; they do not rematerialize the workspace manifest as a repository manifest.
- Workspace selection uses `selected_repository_sources/v2`.
- No filename or schema fallback was added.
