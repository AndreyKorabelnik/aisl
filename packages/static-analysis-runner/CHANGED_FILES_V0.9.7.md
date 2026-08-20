# Changed files — static-analysis-runner 0.9.7

- `static_analysis_runner/io_utils.py` — guarded output validation, ownership marker and marker-gated replacement.
- `static_analysis_runner/execution.py` — non-mutating executable preflight helper.
- `static_analysis_runner/repository.py` — core version preflight before output replacement and expanded protected inputs.
- `static_analysis_runner/suite.py` — preflight ordering and expanded protected inputs.
- `static_analysis_runner/workspace.py` — safe output validation and tool preflight before registration/output replacement.
- `static_analysis_runner/knowledge_layer.py` — validate dependencies and manifests before output creation/replacement.
- `static_analysis_runner/cli.py` — `--replace` disabled by default.
- `static_analysis_runner/version.py`, `pyproject.toml` — version 0.9.7.
- `tests/test_profiles_and_paths.py`, `tests/test_workspace_runner.py`, `tests/test_cli.py` — destructive-output regressions and version checks.
- `README.md`, `docs/CLI.md`, `RELEASE_NOTES_V0.9.7.md`, `TEST_RESULTS.md` — safety and release documentation.
