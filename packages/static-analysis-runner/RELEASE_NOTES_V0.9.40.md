# static-analysis-runner 0.9.40 — official Core catalog consumption

## Changed

- `mechanism-catalog` now requires an official `core_analysis_catalog/v1` produced by `code-analyzer-core`;
- Runner no longer resolves Core profile inheritance or inspects Core Python runtime sources;
- combined catalog schema advanced to `analysis_mechanism_catalog/v4`;
- Core-owned data is exposed under `core_layer`, `foundation_layer` and `core_stage_catalog`;
- Task and Suite layers are linked to Core profiles by the official profile source path;
- canonical Core catalog fingerprint and schema are validated before composition;
- absent Task profiles fail explicitly;
- legacy catalog inputs `--profiles-root`, `--foundation-fragment` and `--core-root` were removed without adapters.

## Ownership boundary

```text
Core catalog
→ profiles, Foundation, runtime stages, evidence outputs, diagnostics

Runner
→ Task, Suite, process/retry/output boundaries

KLC inspection
→ current task_id-based imports and capabilities
```

## Runtime behavior

Repository, workspace, Suite, Task and Knowledge Layer execution paths are unchanged. This iteration changes only the read-only mechanism catalog.
