# knowledge-api 0.19.2 — agent-ready data-model attribute-extension context

Adds `GET /api/knowledge/v1/systems/{system_id}/data-model/attribute-extension-context`.

Knowledge API remains thin. It selects the typed `data-model-attribute-extension-context/v1` artifact and delegates filtering/read behavior to KLC `KnowledgeLayerQuery.list_attribute_extension_join_semantics()`. The API does not inspect DuckDB tables directly and does not classify relationships, compare key expressions, resolve physical tables, choose JOIN predicates or generate SQL.

The response exposes KLC-materialized join semantics, key/reference expressions, SQL anchors, physical candidates, provenance/diagnostics, related object anchors and explicit page-owned gaps.
