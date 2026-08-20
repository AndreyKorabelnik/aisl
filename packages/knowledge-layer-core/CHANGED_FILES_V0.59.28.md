# KLC 0.59.28 changed files

- `knowledge_layer_core/foreign_data_queries.py`
  - preserves FDP technical source/origin interpretation introduced in 0.59.27;
  - fixes the unfiltered FDP path facade so only canonical `source_to_storage_lineage.json` and `storage_to_access_lineage.json` records participate in FDP path/case catalogs;
  - prevents persistence helper payloads, test/mock observations and other non-path artifacts from being mislabeled as storage→access paths.
- `tests/test_persistence_lineage_typed_materialization.py`
  - regression for exact all-path catalog = source→storage + storage→access only.
- version/release/test metadata updated to 0.59.28.
