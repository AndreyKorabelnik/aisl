# Changed files — knowledge-layer-core 0.42.0

- `knowledge_layer_core/topology_contracts.py` — canonical `portfolio-topology/v1` build request contract.
- `knowledge_layer_core/topology_schema.py` — compact standalone topology DuckDB schema without deep lineage/data-model tables.
- `knowledge_layer_core/topology_builder.py` — independent topology-only orchestration path over repository interface catalogs.
- `knowledge_layer_core/__init__.py` — public topology builder/contracts/schema exports.
- `tests/test_portfolio_topology.py` — independent build, deep-exclusion and partial-snapshot integration tests.
- `tests/test_system_interaction_graph.py` — align baseline graph summary with canonical repository coverage count.
- `tests/test_offline_validation.py` — align package-version assertion with 0.42.0.
- `pyproject.toml`, `knowledge_layer_core/version.py` — version 0.42.0.
