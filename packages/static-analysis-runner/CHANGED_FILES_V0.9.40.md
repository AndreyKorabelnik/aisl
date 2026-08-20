# Changed files — 0.9.40

- `static_analysis_runner/mechanism_catalog.py` — consumes and validates `core_analysis_catalog/v1`; removes Core YAML/Python reverse engineering from catalog execution; emits catalog v4.
- `static_analysis_runner/cli.py` — mandatory `--core-catalog`; removed legacy Core-source catalog options.
- `tests/test_mechanism_catalog.py` — official Core catalog fixture, composition tests, fingerprint/schema/profile validation and no-legacy-option test.
- `docs/ANALYSIS_MECHANISM_CATALOG.md` — new ownership and CLI contract.
- `docs/CORE_STAGE_CLASSIFICATION.md` — Core-owned stage classification.
- `docs/CLI.md`, `README.md` — updated command examples and version.
- `pyproject.toml`, `static_analysis_runner/version.py`, `tests/test_cli.py` — version 0.9.40.
