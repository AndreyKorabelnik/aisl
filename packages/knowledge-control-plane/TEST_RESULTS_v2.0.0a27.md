# Test results — analysis-ui 2.0.0a27

- compileall: passed.
- Ready DuckDB registry, manifest validation, path safety and immutable publication: passed.
- Assistant-context, runtime store, Knowledge API publication and orchestration boundary regression: passed.
- Focused total: 24 passed.
- Real smoke: registered the existing 97,792,000-byte `datamart_profile_fl` DuckDB with its real manifest; SHA-256 and 7 capabilities were preserved without re-analysis or copying.
- Full backend/frontend suite: not run; job execution, frontend components, analyzers and Knowledge Layer materialization were unchanged.
