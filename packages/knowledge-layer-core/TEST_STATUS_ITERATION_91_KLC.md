# Test status — iteration 91 KLC

## Focused tests

- `tests/test_sql_analysis_knowledge_layer.py`
- `tests/test_sql_workflow_context.py`

Result: **14 passed, 0 failed**.

Covered:

- schema, indexes, capabilities and build counts for the three new typed tables;
- workflow/config-to-SQL reachability;
- placeholder binding scoped by an observed file path;
- no global same-name substitution;
- bare `$load_type` placeholder after an underscore;
- exact suffix matching of `inc` and `arc` files;
- exact source-directory narrowing that prevents branch crossing;
- preservation of both branches when the workflow itself does not resolve `$load_type`;
- existing workflow-binding and target-lineage contracts in the affected SQL module.

## Real repository smoke

Source: unchanged code-analyzer-core 0.43.7 canonical SQL artifact for `datamart_profile_fl`.

Result:

- KLC build: complete;
- 418 file references;
- 1,100 context paths;
- 248 placeholder binding resolutions;
- exactly two three-hop `t0_individual` paths, one `dml_inc` and one `dml_arc`;
- no mixed branch paths;
- validation: complete.

## Deliberately not run

The full KLC suite was not run. Common workspace ingestion, UCP data-model relationships, topology, portfolio, attribute paths and non-SQL query surfaces were not modified. The focused SQL tests and one real repository build cover the changed contour.
