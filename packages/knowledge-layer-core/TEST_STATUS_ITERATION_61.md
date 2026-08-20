# Test status — iteration 61

Date: 2026-07-31

## Focused SQL contract

- `tests/test_sql_analysis_knowledge_layer.py`: 3 passed.
- Relevant query/contracts/infrastructure set: 30 passed.

## Existing KLC regression

The suite was executed in isolated groups because the historical heavy workspace module can hang
when accumulated after the rest of the suite in one Python process.

- all modules except `test_workspace_data_model.py`: 144 passed, 13 skipped;
- `test_workspace_data_model.py`, first half: 15 passed;
- `test_workspace_data_model.py`, second half: 15 passed.

Total factual result:

- 174 passed;
- 13 skipped;
- 0 failed.

## Real SQL artifact

Input:

- `datamart_profile_fl` canonical `sql-analysis/v1`;
- content fingerprint `5fffb63d9f7e5ebbdd2261b13aec0e33ee7eae9ef0cc8b3b324edfc3674a6c69`.

Result:

- build status: complete;
- source analysis status: partial;
- 27,600 facts imported;
- duplicate IDs: 0;
- orphan non-null column relation references: 0;
- materialization time: approximately 4 seconds;
- peak RSS: approximately 296 MB;
- DuckDB size: approximately 81 MB;
- physical relation inventory: 89 identities;
- physical-template inventory: 195 identities;
- relation-field query returned template identities with only their linked field usages.

## Packaging checks

Completed against the release candidate and repeated from the final clean extraction:

- `compileall`: passed;
- source-tree manifest: passed;
- ZIP integrity: passed;
- focused SQL tests: passed;
- split full regression: passed (`174 passed`, `13 skipped`);
- real artifact smoke build/query: passed.

Runtime-only wheel dependencies used for validation were installed in an isolated external directory
and are not included in the source ZIP.
