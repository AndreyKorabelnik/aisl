# Changed files — Analysis UI 2.0.0a73

Primary runtime changes:

- `src/analysis_ui/runtime/knowledge_contracts.py` — default discovery now uses the Analysis UI packaged runtime-contract bundle rather than source `validation/` directories.
- `src/analysis_ui/resources/runtime_contracts/bundle-manifest.json` — bundle metadata.
- `src/analysis_ui/resources/runtime_contracts/core-evidence-contract-catalog.json` — compatible Core evidence contract catalog.
- `src/analysis_ui/resources/runtime_contracts/knowledge-materialization-catalog.json` — compatible KLC materialization catalog.
- `src/analysis_ui/resources/runtime_contracts/knowledge-catalog.json` — compatible Runner Knowledge catalog.
- `pyproject.toml` — package-data declaration and version 2.0.0a73.
- `VERSION`, `src/analysis_ui/__init__.py` — version update.
- `tests/test_knowledge_execution_ui.py` — packaged-bundle/no-validation and override tests.
- `README.md` — one-shot CLI and runtime-contract deployment notes.
- `scripts/verify_knowledge_execution_architecture.py` — release version update.

The `analysis-ui run` implementation from the preceding CLI release remains present in:

- `src/analysis_ui/cli.py`
- `src/analysis_ui/runtime/one_shot.py`
- `tests/test_one_shot_cli.py`

No Core, Runner, KLC, Knowledge API, Reporting or Assistant source was changed in this release.
