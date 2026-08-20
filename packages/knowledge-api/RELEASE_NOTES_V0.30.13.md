# knowledge-api 0.30.13

Adds a thin compact exact-read projection for already-published System Interactions knowledge.

- New `GET /api/knowledge/v1/systems/{system_id}/interactions/{interaction_id}/guidance` endpoint.
- The endpoint groups only by exact published `interaction_id` / `boundary_interaction_id`; it does not rematch endpoints, infer target systems, upgrade confidence or create field mappings.
- Surfaces source outbound → target ingress, KLC-owned match status/confidence/basis, bounded execution contexts and bounded field contracts in one action-oriented response.
- Removes duplicated heavy `payload_json` from the LLM-facing projection while preserving canonical detailed interaction endpoints for drill-down.
- Truncation is explicit per boundary interaction; absence of the optional field-contract product is returned as `not_available`, not silently treated as empty knowledge.
- Depends on `knowledge-integration==0.1.12`.
