# knowledge-layer-core 0.51.3

- Added `KnowledgeLayerQuery.get_sql_column_usage_context`.
- Exposes one SQL column usage with its statement, SELECT scope, scoped relations, observed fields, JOINs and projections.
- Does not infer or rewrite ambiguous ownership.
