# Changed files — code-analyzer-core 0.43.27

## Added

- `code_analyzer_core/evidence_runtime.py` — Core-owned analyzer registry and generic evidence execution runtime.
- `code_analyzer_core/resources/core_evidence_execution_request_v1.schema.json`.
- `code_analyzer_core/resources/core_evidence_execution_result_v1.schema.json`.
- `HANDOVER_GENERIC_EVIDENCE_RUNTIME_V0.43.27.md`.
- `RELEASE_NOTES_V0.43.27.md`.
- `TEST_STATUS_V0.43.27.md`.

## Changed

- `code_analyzer_core/cli.py` — added `evidence-execute`.
- `code_analyzer_core/evidence_contracts.py` — runtime publication comes from the Core registry.
- `code_analyzer_core/pipeline.py` — removed hidden Java typed-evidence publication.
- `code_analyzer_core/prepared_artifacts/java_type_structure_evidence.py` — retained only the domain builder and canonical artifact contract.
- `code_analyzer_core/resources/core_evidence_contract_definitions_v1.json`.
- `code_analyzer_core/resources/core_target_contract_definitions_v1.json`.
- `code_analyzer_core/target_contracts.py`.
- `code_analyzer_core/__init__.py`, `pyproject.toml` — version 0.43.27.
- `README.md` and affected tests.
