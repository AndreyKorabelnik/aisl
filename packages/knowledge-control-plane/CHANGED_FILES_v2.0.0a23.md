# Changed files — analysis-ui 2.0.0a23

- `src/analysis_ui/runtime/store.py` — always close SQLite connections after each transactional operation.
- `tests/test_runtime_store_lifecycle.py` — verify every opened connection is closed.
- `pyproject.toml` — disable the external ddtrace pytest plugin for this suite.
- `scripts/check.sh` — ordinary grouped runtime pytest execution.
- `scripts/run_pytest_hard_exit.py` — removed.
- `tests/test_module_baseline.py` — guard against reintroducing the hard-exit workaround.
- release metadata, OpenAPI version and source manifest.
