# Changed files — 0.9.25

## Production

- `pyproject.toml` — version `0.9.25`.
- `static_analysis_runner/version.py` — runtime version `0.9.25`.
- `static_analysis_runner/profiles.py` — strong semantic selection of Java or SQL analyzer.
- `static_analysis_runner/repository.py` — SQL routing, SQL core version floor,
  canonical artifact validation, SQL status in manifests, and explicit KLC boundary.
- `static_analysis_runner/sql_artifact.py` — `sql-analysis/v1` streaming validator.

## Tests

- `tests/test_sql_repository_runner.py` — SQL routing, version, valid/invalid artifact,
  path safety, malformed manifest, and deferred materialization contracts.
- `tests/conftest.py` — isolated subprocess test doubles use the active interpreter
  without unrelated site initialization.
- `tests/test_cli.py` — version expectation.
- `tests/test_repository_runner.py` — current runner version expectation.

## Documentation and validation

- `README.md`
- `docs/CLI.md`
- `docs/CONTRACTS.md`
- `RELEASE_NOTES_V0.9.25.md`
- `CHANGED_FILES_V0.9.25.md`
- `TEST_STATUS_ITERATION_60.md`
- `HANDOVER_ITERATION_60.md`
- `validation/iteration-60/test_all.log`
- `validation/iteration-60/real-sql-e2e-summary.json`
- `validation/iteration-60/quick-status.txt`
- `SOURCE_TREE_MANIFEST.sha256`
