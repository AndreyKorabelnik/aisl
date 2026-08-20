# knowledge-layer-core 0.59.47

## Purpose
Expose already-materialized Prepared Knowledge needed by a minimal external-LLM Consumer without introducing a second knowledge layer or any Producer fallback.

## Changes
- Added read-only `KnowledgeLayerQuery.list_relation_materializations(...)` over canonical `cross_artifact_relation_materialization`.
- Added read-only `KnowledgeLayerQuery.get_sql_query_context(...)` over canonical SQL marts.
- Query-context selection chooses a unique root scope only when it is unique; multiple roots remain explicit ambiguity.
- Returned context includes statement, selected/root scope, child scopes, relations/observed fields, joins, final projections, counts, and diagnostics.
- Reuses existing `common.relation-materialization` and `common.sql-analysis` capabilities.

## Non-changes
- No Core changes.
- No Runner changes.
- No materialization/schema/capability changes.
- No source parsing or query-time Producer execution.
- No compatibility adapter or second discovery path.
