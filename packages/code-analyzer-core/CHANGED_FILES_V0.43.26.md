# Changed files — code-analyzer-core 0.43.26

## Added

- `code_analyzer_core/prepared_artifacts/java_type_structure_evidence.py`
- `tests/test_java_type_structure_evidence.py`
- runtime typed artifact `evidence/java-type-structure-evidence.json`
- diagnostics status `diagnostics/java_type_structure_evidence_status.json`
- manifest registration under `prepared_artifacts.java_type_structure_evidence`
- evidence-coverage counters and stage status
- direct and Foundation-reuse byte-parity tests
- real-repository smoke status and handover notes

## Updated

- `code_analyzer_core/pipeline.py`
- `core_evidence_contract_catalog/v1`: contract status is `runtime_published`
- package version: `0.43.25` → `0.43.26`
- release notes and validation artifacts

## Transitional execution binding

The independent artifact is temporarily executed as an internal phase of `java_source_observation_build`. Its semantic identity is only `artifact_kind + schema_version`. No Runner registration, KLC materialization or UI change is included.
