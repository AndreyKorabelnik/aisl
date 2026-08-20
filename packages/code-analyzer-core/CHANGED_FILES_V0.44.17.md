# Core 0.44.17 changed files

- `code_analyzer_core/target_contracts.py`: removed obsolete `legacy_fallback` marker from current runtime assessment.
- `code_analyzer_core/prepared_artifacts/*.py`: removed obsolete Task/Suite-profile and legacy-fallback markers from current evidence contracts/provenance/payload manifests.
- targeted tests: updated to verify marker absence while preserving typed evidence behavior.
- `code_analyzer_core/__init__.py`, `pyproject.toml`: version 0.44.17.
