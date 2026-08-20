# analysis-ui 2.0.0a6

Iteration 6 adds production diagnostics and support tooling without changing the UI2 1.4.7 visual surface or data-model API ownership.

## Added

- `analysis-ui doctor` and `analysis-ui doctor --json`;
- runtime diagnostics for configured tools, paths, TLS files, SQLite integrity, disk space, frontend build, Git and active jobs;
- log filtering by level, stream, stage and text search;
- downloadable sanitized job logs;
- reproducible command history derived from already-redacted execution logs;
- typed comparison of two jobs, including status, duration, profile, failure, stages and artifact kinds;
- diagnostics ZIP generation and registration as a `diagnostics_bundle` artifact;
- frontend typed-client methods for all new operations;
- ADR-008 defining metadata-only diagnostics bundles.

## Security

Diagnostics bundles do not include:

- source repositories;
- artifact payloads, Knowledge Layers or report datasets;
- environment values;
- Bitbucket/LLM tokens;
- client private keys or TLS certificate contents.

Only protected environment-variable presence is reported as booleans.

## Preserved

- six data-model endpoints remain outside generic API ownership;
- all 20 Vue template/style sections remain byte-identical to UI2 1.4.7;
- existing repository/workspace/full-pipeline jobs and retry behavior are unchanged;
- generic assistant execution remains capability-gated.
