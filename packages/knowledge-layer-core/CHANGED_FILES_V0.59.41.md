# KLC 0.59.41 changed files

Legacy Cleanup Block 3 removes the live generic `analysis_record` compatibility path from typed interaction/value-flow materialization.

Changed runtime files:
- `knowledge_layer_core/interaction_contracts.py` — field-contract materializer reads canonical typed value-flow evidence relation; supports an explicit schema-qualified typed relation for KLC-to-KLC composition.
- `knowledge_layer_core/interaction_field_contract_knowledge_builder.py` — removed temporary `analysis_record` compatibility table and `legacy_contract_published` tombstone.
- `knowledge_layer_core/value_flow.py` — removed `value_flow_evidence_record -> analysis_record` dual-read; retained `_has_relation` only for optional current typed marts.
- `knowledge_layer_core/interaction_graph.py` — removed typed interaction boundary -> `analysis_record` fallback.
- `tests/test_typed_relation_legacy_rejection.py` — negative old-contract tests.
- `tests/test_interaction_field_contract_typed_materialization.py` — verifies no generic `analysis_record` is published.
- version metadata updated to 0.59.41.
