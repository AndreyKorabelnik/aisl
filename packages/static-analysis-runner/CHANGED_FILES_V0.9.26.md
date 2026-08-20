# Changed files — static-analysis-runner 0.9.26

## Production code

- `static_analysis_runner/repository.py`
  - added automatic SQL/data-model Knowledge Layer mode selection;
  - added SQL-specific KLC builder invocation;
  - removed the SQL materialization prohibition;
  - verifies the KLC source fingerprint against the validated core artifact.
- `static_analysis_runner/sql_artifact.py`
  - removed the hard-coded 17-stream contract from runner validation;
  - validates every manifest-declared fact stream generically;
  - rejects duplicate types/paths and invalid declared identifiers.
- `static_analysis_runner/cli.py`
  - `--knowledge-mode` now defaults to `auto`.
- `static_analysis_runner/version.py`
  - version `0.9.26`;
  - minimum KLC version `0.50.0`.
- `pyproject.toml`
  - package version and optional KLC dependency updated.

## Tests

- `tests/test_sql_repository_runner.py`
  - successful SQL materialization through auto mode;
  - explicit mode mismatch;
  - additive manifest stream accepted by runner;
  - duplicate fact type rejected;
  - real KLC 0.50.0 materialization contract.
- version and compatibility expectations updated across existing tests.

## Documentation and validation

- `README.md`;
- `docs/CONTRACTS.md`;
- `RELEASE_NOTES_V0.9.26.md`;
- `HANDOVER_ITERATION_62.md`;
- `TEST_STATUS_ITERATION_62.md`;
- `validation/iteration-62/*`.
