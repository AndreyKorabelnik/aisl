# Changed files — Analysis UI 2.0.0a70

- `src/analysis_ui/cli.py` — added `analysis-ui run` terminal entry point.
- `src/analysis_ui/runtime/one_shot.py` — thin one-shot adapter over the existing RuntimeContext / JobManager path.
- `tests/test_one_shot_cli.py` — tests for repository/workspace request construction and direct JobManager lifecycle.
- `tests/test_module_baseline.py` — version baseline updated.
- `README.md` — terminal run example and service boundary.
- `pyproject.toml`, `VERSION`, `src/analysis_ui/__init__.py`, frontend package metadata — version bump to 2.0.0a70 / alpha.70.
- `RELEASE_NOTES_v2.0.0a70.md` — release note.
