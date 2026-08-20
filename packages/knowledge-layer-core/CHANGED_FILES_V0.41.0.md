# Changed files — knowledge-layer-core 0.41.0

- `knowledge_layer_core/interaction_coverage.py` — new per-repository topology and outbound matching coverage materializer.
- `knowledge_layer_core/interaction_graph.py` — match diagnostics now publish nullable confidence for matched outbounds.
- `knowledge_layer_core/interaction_islands.py` — island-level analysis/matching coverage and matched/ambiguous/unresolved aggregates.
- `knowledge_layer_core/suite_schema.py` — canonical coverage table, expanded island contract, diagnostic confidence, suite schema v10.
- `knowledge_layer_core/suite_builder.py` — coverage materialization and capability publication.
- `knowledge_layer_core/query.py` — repository coverage query and expanded island/graph projections.
- `knowledge_layer_core/evidence.py` — repository coverage evidence command.
- `tests/test_system_interaction_graph.py` — confirmed/probable/ambiguous/unresolved and island coverage regression scenarios.
- `pyproject.toml`, `knowledge_layer_core/version.py` — version 0.41.0.
