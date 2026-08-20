# Changed files — knowledge-layer-core 0.59.35

- `knowledge_layer_core/attribute_extension_context_queries.py` — KLC-owned read/query contract for materialized agent-ready attribute-extension join semantics, related object anchors and explicit gaps. Filtering/decoding only; no new inference.
- `knowledge_layer_core/query.py` — exposes `KnowledgeLayerQuery.list_attribute_extension_join_semantics()`.
- `tests/test_attribute_extension_context_query.py` — read-contract regression for encoded-reference semantics, anchors, gaps and explicit not-available behavior.
- `knowledge_layer_core/version.py`, `pyproject.toml` — version 0.59.35.
