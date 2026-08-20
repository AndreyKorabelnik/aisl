# Test results — static-analysis-runner 0.9.31

Environment used for the full run:

- Python 3.13;
- knowledge-layer-core 0.53.4 from the supplied baseline;
- DuckDB 1.5.5 from the supplied wheel.

Results:

- `compileall` — passed;
- focused portfolio contracts/runner/CLI tests — 18 passed;
- real KLC compact-result integration smoke — passed, including one failed repository represented as `analysis_status=failed`;
- full Runner suite — 83 passed in 28.33 seconds;
- source manifest validation — passed;
- ZIP re-extraction validation — passed.

Known limitations:

- the user-facing islands JSON export is not included yet; KLC DuckDB and manifests are produced;
- real Bitbucket credentials/network were not available, so Bitbucket pagination is verified with a deterministic API fixture and clone lifecycle with local Git repositories;
- Kafka boundaries and matching remain intentionally deferred until after the HTTP MVP.
