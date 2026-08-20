# static-analysis-runner 0.9.28

- Added packaged canonical analysis suites under `static_analysis_runner/config/suites`.
- Added explicit `--suite-id` to repository and workspace commands.
- `foreign-data-persistence` can now be invoked without exposing a filesystem path to the UI.
- Unknown suite IDs fail explicitly; no fallback suite selection is performed.
