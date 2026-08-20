# Changed files — knowledge-layer-core 0.53.4

- `knowledge_layer_core/foreign_data_queries.py`
  - removes table-level mechanical cases;
  - builds exact storage-field/path-pair cases;
  - requires confirmed maturity on both path segments;
  - publishes table aggregation only in `storage_summaries`;
  - keeps unmatched source/access paths as explicit unresolved cases.
- `tests/test_suite_scope.py`
  - updates the canonical FDP case contract;
  - adds a regression preventing cross-contamination between different fields and paths of one table.
- `pyproject.toml`, `knowledge_layer_core/version.py`
  - version `0.53.4`.
- `AT900_FDP_EXACT_CASES_V0.53.4.json`
  - real AT900 validation excerpt.
