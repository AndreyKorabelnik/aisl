# knowledge-layer-core 0.59.6

Adds deterministic knowledge-quality representations over the restored value-flow graph.

- One canonical `repository_value_flow_edge` graph remains authoritative.
- `confidence=confirmed` normalizes to `knowledge_class=confirmed`.
- `confidence=probable` normalizes to `knowledge_class=derived`.
- Other materialized relationships normalize to `knowledge_class=candidate`.
- Adds deterministic `strict`, `working`, and `exploratory` SQL views.
- Attribute-path results expose aggregate `knowledge_class`; default traversal uses the `working` view.
- No LLM scoring and no changes to matching/evidence extraction.
