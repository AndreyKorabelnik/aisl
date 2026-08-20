# knowledge-integration 0.1.3

- Adds canonical model-facing result projections for oversized code-declared data-model retrievals.
- `search_declared_data_objects` is represented as bounded discovery cards; raw fields are not silently treated as absent and exact object reads are required for field evidence.
- `get_declared_data_object` preserves all effective fields and relationships in a compact structural projection while removing repeated AST/detail payloads.
- Every projection exposes explicit truncation/continuation/coverage metadata; raw Knowledge API responses remain the provenance source of truth outside LLM context.
