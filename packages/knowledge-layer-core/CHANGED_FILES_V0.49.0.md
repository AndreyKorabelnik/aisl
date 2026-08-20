# Changed files — knowledge-layer-core 0.49.0

## Production

- `knowledge_layer_core/interaction_contracts.py`
  - field-contract schema v2;
  - exact observed nested-boundary contracts;
  - strict initializer-based method-reference fallback;
  - collection-member builder reconstruction without an execution-context gate;
  - direct outbound-boundary flow provenance.
- `knowledge_layer_core/value_flow.py`
  - value-flow schema v6;
  - synthetic reconstructed wire nodes;
  - probable reconstructed serialization and HTTP transport edges;
  - reconstruction evidence packets.
- `knowledge_layer_core/suite_schema.py`
  - suite schema v17.
- `knowledge_layer_core/version.py`, `pyproject.toml`
  - package version 0.49.0.

## Tests and documentation

- `tests/test_system_interaction_graph.py`
  - regression without an explicit method-reference artifact or execution context;
  - probable reconstructed contracts, transport, resolver path and guard checks.
- `tests/test_offline_validation.py`
  - expected package version updated.
- `docs/SYSTEM_INTERACTION_FIELD_CONTRACTS_V2.md`
  - canonical v2 contract documentation; v1 document removed.
- `README.md`
- `RELEASE_NOTES_V0.49.0.md`
- `HANDOVER_ITERATION_46.md`
- `TEST_STATUS_ITERATION_46.md`
- `VALIDATION_ITERATION_46.md`
- `VALIDATION_ITERATION_46.json`
