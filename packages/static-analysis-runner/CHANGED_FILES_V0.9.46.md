# Changed files — 0.9.46

- `static_analysis_runner/evidence_artifacts.py` — strict validation and registration of `java-type-structure-evidence/v1` by `artifact_kind + schema_version`.
- `static_analysis_runner/repository.py` — repository-run analyzer execution and typed evidence registries; evidence fingerprints included in the run fingerprint.
- `static_analysis_runner/suite.py` — task-local preservation and summary of registered typed evidence without Task semantic routing.
- `static_analysis_runner/execution_result_contracts.py` — current manifest assessment updated for the first registered Java evidence artifact.
- `static_analysis_runner/knowledge_architecture_audit.py` — official Core Evidence Contract Catalog input and current contract/runtime/Runner gate evaluation.
- `static_analysis_runner/cli.py` — `--core-evidence-contracts` for the generic knowledge architecture audit and updated execution-contract next-step reporting.
- `tests/test_java_type_structure_registration.py` — repository success, invalid fingerprint failure and Suite propagation.
- `tests/test_repository_runner.py`, `tests/test_repository_suite.py`, `tests/test_execution_result_contracts.py`, `tests/test_knowledge_architecture_audit.py`, `tests/test_cli.py` — affected contracts and runtime regression.
- `README.md`, `docs/CLI.md`, `docs/CONTRACTS.md`, `docs/KNOWLEDGE_ARCHITECTURE_AUDIT.md` — first typed evidence registration and audit input documentation.
- `pyproject.toml`, `static_analysis_runner/version.py` — version 0.9.46.
