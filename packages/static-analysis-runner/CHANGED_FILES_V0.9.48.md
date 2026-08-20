# Changed files — static-analysis-runner 0.9.48

## Added

- `static_analysis_runner/evidence_executor.py` — generic Core evidence request compiler, executor and artifact registrar.
- `tests/test_evidence_executor.py`.
- `HANDOVER_GENERIC_CORE_EVIDENCE_EXECUTOR_V0.9.48.md`.
- `RELEASE_NOTES_V0.9.48.md`.
- `TEST_RESULTS_V0.9.48.md`.

## Deleted

- `static_analysis_runner/evidence_artifacts.py` — Java-specific evidence registration.
- `tests/test_java_type_structure_registration.py`.

## Changed

- `static_analysis_runner/cli.py` — added `evidence-execute`; `knowledge-catalog` requires the Core evidence catalog.
- `static_analysis_runner/knowledge_planning.py` — removed the static Runner list of Core evidence families; producer/runtime bindings come from `core_evidence_contract_catalog/v1`.
- `static_analysis_runner/repository.py` — removed implicit legacy typed-artifact registration.
- `static_analysis_runner/execution_result_contracts.py`.
- `static_analysis_runner/knowledge_architecture_audit.py`.
- `static_analysis_runner/version.py`, `pyproject.toml` — version 0.9.48.
- `README.md`, `docs/CLI.md`, `docs/CONTRACTS.md` and affected tests.
