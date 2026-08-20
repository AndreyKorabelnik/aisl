# Test status — iteration 37

- Python `compileall`: passed.
- `tests/test_system_interaction_graph.py`: 21 passed in two isolated batches.
- Focused query/evidence/suite/contract tests: 24 passed.
- All other test files except `test_workspace_data_model.py`: 121 passed, 13 skipped.
- Total completed regression: 142 passed, 13 skipped.
- New regression proves:
  - configured repository aliases can disambiguate identical HTTP routes;
  - boundary inventory publishes `system_id`, `project_id` and configured aliases;
  - query and evidence filters expose the metadata;
  - one project can contain multiple independent strict islands.

Known test limitation: a single cumulative interaction pytest process again stalled after substantial progress because of the known DuckDB/process issue. The same 21 tests completed successfully in two isolated batches. `test_workspace_data_model.py` was not rerun because it repeatedly exceeds the available process timeout and the changed topology metadata contour does not modify data-model materialization.
