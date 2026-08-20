# code-analyzer-core 0.43.27 — generic evidence runtime

Core now owns a generic runtime for typed evidence analyzers. Analyzer selection is based only on `artifact_kind + schema_version`; the first registered family is `java-type-structure-evidence/v1`.

## Architecture

- Added `core_evidence_runtime/v1`.
- Added request/result contracts `core_evidence_execution_request/v1` and `core_evidence_execution_result/v1`.
- Added a Core-owned registry mapping evidence identity to analyzer handler.
- Removed automatic typed-evidence publication from `analyze-java`.
- Unknown evidence contracts fail explicitly.
- Task, Suite, Profile and knowledge IDs are not runtime dispatch keys.
- No legacy fallback, compatibility adapter or dual-write is retained.

## Validation

The release is validated by the full Core test suite and the real Runner → Core → KLC end-to-end smoke recorded in `validation/generic-core-evidence-e2e-smoke-v0.43.27.json`.
