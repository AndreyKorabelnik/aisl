# Test status — iteration 72 API

- `compileall`: passed.
- Focused SQL API, contract/OpenAPI and runtime tests: 23 passed, 0 failed.
- Canonical OpenAPI regenerated and verified.
- Synthetic context contract: passed with two relations, one ambiguous field, one JOIN and one projection.
- Missing usage contract: passed (`404 sql_column_usage_not_found`).
- Real datamart publication and context query: passed.
- UCP and datamart systems queried through the same Knowledge API catalog: passed.
- Full unrelated data-model, publication-administration and relationship regression was not run.
