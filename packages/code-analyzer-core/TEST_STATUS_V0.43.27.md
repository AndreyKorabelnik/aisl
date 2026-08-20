# Test status — code-analyzer-core 0.43.27

## Final checks

- `compileall`: passed.
- Full Core regression: **577 passed in 9.92s**.
- Generated contract fingerprints reproduce the real end-to-end smoke contracts byte-for-byte.
- Generic evidence release validation: passed.
- Real end-to-end smoke: passed.

## End-to-end path

```text
knowledge_profile/v2
→ knowledge_resolution_plan/v2
→ core_evidence_execution_request/v1
→ core_evidence_runtime/v1
→ static_repository_analysis_run_manifest/v1
→ knowledge_materialization_runtime/v1
→ knowledge_materialization_execution_result/v1
```

The smoke produced three Java types, five declared fields, one inheritance relation and a complete `code-declared-data-model/v1` result with five capabilities and no gaps.

Logs and artifacts are under `validation/generic-evidence-runtime-v0.43.27/`.
