# static-analysis-runner 0.9.48 — generic Core evidence executor

Runner now executes the complete upper half of the generic knowledge path without an evidence-family branch:

```text
knowledge_profile/v2
→ knowledge_resolution_plan/v2
→ core_evidence_execution_request/v1
→ Core core_evidence_runtime/v1
→ static_repository_analysis_run_manifest/v1
```

## Architecture

- Compiles Core evidence requirements from the resolution plan and official Core evidence catalog.
- Invokes only `code-analyzer-core evidence-execute`.
- Validates and registers arbitrary typed artifacts by `artifact_kind + schema_version`.
- Removes the Java-specific registrar and the static Runner list of Core evidence contracts.
- Keeps Task, Suite, Profile and knowledge IDs out of analyzer routing.
- Does not support legacy fallback, compatibility adapters or dual-write.

The existing generic KLC materialization executor remains unchanged conceptually and consumes the resulting registered artifacts.
