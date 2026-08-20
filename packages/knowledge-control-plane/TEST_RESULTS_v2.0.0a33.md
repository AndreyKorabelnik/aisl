# Test results 2.0.0a33

Status: **passed**

Focused regression:

- **39 passed in 18.30s**
- covered prepared assistant contexts, pinned PDM revision, context frontend, publication contract, profile discovery, generic API contract, module baseline and PDM knowledge-only pipeline
- TypeScript/Vue syntax validation: passed
- `compileall`: passed
- OpenAPI validation: passed
- frontend boundary, portability and visual-baseline checks: passed
- source manifest and ZIP integrity: passed

Real Analysis UI PDM pipeline:

```text
PDM file
→ standard full_pipeline job
→ static-analysis-runner physical-model
→ physical-model/v1
→ typed Knowledge Layer materialization
→ immutable Knowledge API revision
```

Observed:

- checkout: skipped
- static analysis: succeeded
- Knowledge Layer materialization: succeeded
- report: skipped
- publication: succeeded
- published artifact: `knowledge-layer.duckdb`
- media type: `application/vnd.duckdb`
- no report generated

The full platform suite was not run. A broader exploratory test invocation was stopped by the environment time limit and is not counted as a completed result.
