# Changed files — knowledge-layer-core 0.43.0

- `knowledge_layer_core/value_flow.py` — canonical repository-local typed value nodes and direct observed value-flow edges.
- `knowledge_layer_core/suite_schema.py` — suite schema v11; removes eager attribute/object/origin tables and adds direct graph tables.
- `knowledge_layer_core/suite_builder.py` — replaces four eager lineage materializers with one direct graph materializer.
- `knowledge_layer_core/query.py` — repository value-node and direct-edge query surfaces; removes legacy eager-lineage queries.
- `knowledge_layer_core/evidence.py` — direct value-flow evidence tools; removes legacy eager-lineage tools.
- `knowledge_layer_core/__init__.py` — direct value-flow public exports.
- `knowledge_layer_core/interaction_lineage.py` — removed.
- `knowledge_layer_core/interaction_response_lineage.py` — removed.
- `knowledge_layer_core/interaction_object_lineage.py` — removed.
- `knowledge_layer_core/interaction_value_origins.py` — removed.
- `docs/REPOSITORY_DIRECT_VALUE_FLOW_V1.md` — canonical direct graph contract and removed eager models.
- `docs/SYSTEM_INTERACTION_OBJECT_LINEAGE_V1.md` — removed.
- `docs/SYSTEM_INTERACTION_VALUE_ORIGINS_V1.md` — removed.
- `tests/test_repository_value_flow.py` — typed nodes, direct edge classification, origin nodes, no transitive fabrication and production filtering.
- `tests/test_system_interaction_graph.py` — canonical direct-flow expectations; obsolete eager-lineage scenarios removed.
- `tests/test_portfolio_topology.py` — confirms topology-only artifact excludes direct deep value-flow tables.
- `tests/test_offline_validation.py`, `pyproject.toml`, `knowledge_layer_core/version.py` — version 0.43.0.
