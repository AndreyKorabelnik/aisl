# Test status — iteration 40

- Python `compileall`: passed.
- Focused direct-flow/topology/interaction regression: 14 passed.
- Schema/manifest/query/evidence focused packages: 28 passed.
- Full non-heavy regression, executed as isolated test-file processes: 134 passed, 13 skipped.
- `test_system_interaction_graph.py`: 10 passed in two isolated groups.
- `test_workspace_data_model.py` was not run because it is the known heavy fixture and this block does not change data-model materialization.
- A monolithic combined process was abandoned after the known accumulated DuckDB timeout behavior; the same tests were completed in isolated processes.
- Archive extraction, source manifest verification and import/direct-flow smoke are required during packaging.
