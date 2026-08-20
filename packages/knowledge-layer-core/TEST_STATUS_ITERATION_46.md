# Test status — iteration 46

## Fast mandatory set

The iteration was verified with short isolated pytest processes to avoid the known cumulative
DuckDB stall seen in long-lived combined runs.

- `compileall` for `knowledge_layer_core` and tests: passed;
- `tests/test_repository_value_flow.py`: 9 passed;
- `tests/test_attribute_paths.py`: 7 passed;
- `tests/test_system_interaction_graph.py`: 10 passed in isolated processes;
- `tests/test_query.py`: 4 passed;
- `tests/test_evidence.py`: 4 passed;
- `tests/test_suite_scope.py`: 5 passed;
- `tests/test_offline_validation.py`: 10 passed;
- `tests/test_portfolio_topology.py`: 2 passed in isolated processes;
- `tests/test_contracts.py`: 11 passed.

Focused total: **62 passed, 0 failed**.

The full heavy regression was not run because this is a bounded change to nested request-contract
reconstruction. The previous full block regression was completed at iteration 44.

## Real validation

The final `0.49.0` code rebuilt the frozen four-repository validation artifact:

- 8 boundary interactions;
- 0 execution contexts;
- 231 interaction field contracts;
- 3,849 value nodes;
- 2,336 direct value-flow edges.

For `updatePhoneFlags`:

- transport paths: 2 -> 7;
- reconstructed nested paths: 5;
- manually proven mappings reaching target controller parameters: 5/5;
- all results: `probable_complete`;
- confidence promotions: 0;
- the conditional `endDate` guard is retained.

## Clean-archive smoke

From a clean unpacked delivery:

- internal source manifest: 309 files verified;
- imported package/schema versions matched the release;
- nested reconstruction regression, probable resolver evidence and local HTTP wire materialization:
  **3 passed**.
