# Release notes — code-analyzer-core 0.41.7

Iteration 54 binds SQL write targets to projections from the actual top-level output scope.

## Changes

- Added canonical `sql_write_target` facts for INSERT, INSERT OVERWRITE, CTAS, and CREATE VIEW/TABLE targets.
- Added canonical `sql_target_projection_binding` facts linking target columns to ordered scoped projections.
- Explicit INSERT target-column lists are mapped by ordinal and confirmed when projection counts match.
- CTAS/create-view output names define confirmed target columns.
- INSERT statements without an explicit target-column list retain projection-name mappings as `inferred`, not confirmed.
- UNION/INTERSECT/EXCEPT output branches are bound independently to the same target-column ordinals.
- Wildcard projections remain unresolved rather than being expanded without schema evidence.
- DDL column declarations without a SELECT source are classified as `no_select_source`; they are not mistaken for field mappings.
- Target bindings use only top-level output scopes and never aggregate projections from nested CTEs or derived queries.

## Compatibility

No compatibility adapter is provided. Existing mart-column lineage is not yet replaced; the new write-target and projection-binding facts are the canonical input for the next scoped lineage iteration.
