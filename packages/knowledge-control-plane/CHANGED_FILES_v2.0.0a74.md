# Changed files — Analysis UI 2.0.0a74

- `src/analysis_ui/resources/runtime_contracts/*` — regenerated current Core 0.44.11 / Runner 0.10.6 / KLC 0.59.16 contract bundle.
- `src/analysis_ui/runtime/knowledge_contracts.py` — validates bundle v2 manifest, checksums, versions and catalog fingerprints.
- `tests/test_knowledge_execution_ui.py` — current-baseline and bundle-integrity regressions.
- `pyproject.toml`, `VERSION`, `src/analysis_ui/__init__.py` — version 2.0.0a74.
- `RELEASE_NOTES_v2.0.0a74.md`, `CHANGED_FILES_v2.0.0a74.md` — release documentation.

`analysis-ui run` implementation remains the same shared JobManager execution path.
