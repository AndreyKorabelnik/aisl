# KLC 0.59.27 changed files

- `knowledge_layer_core/foreign_data_queries.py`
  - surfaces technical FDP source/origin interpretation from typed persistence evidence (`source_kind`, source-boundary maturity and lineage maturity);
  - preserves the distinction between technical external ingress and a named/business source-system decision.
- `tests/test_persistence_lineage_typed_materialization.py`
  - regression coverage for `confirmed_external_ingress` on confirmed Kafka source→storage evidence.
- version/release/test metadata updated to `0.59.27`.
