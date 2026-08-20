# Release notes — code-analyzer-core 0.41.6

Iteration 53 adds scoped SQL projections and column usages, creating the first reliable table-to-used-field inventory.

## Changes

- Added canonical `sql_projection` facts bound to one `sql_select_scope`.
- Added canonical `sql_column_usage` facts for each column occurrence inside its nearest SELECT scope.
- Column usages are classified by semantic role: projection, join, filter, group-by, having, order-by, window partition, or window order.
- Qualified columns resolve through aliases local to the current scope, with optional lookup in a parent scope for correlated references.
- Unqualified columns resolve only when one relation is available in the scope; multiple candidates remain explicitly ambiguous.
- Output aliases are recognized in ORDER BY/GROUP BY/HAVING but are not confused with source columns in the SELECT list.
- Projection facts reference only column usages from their own scope.
- Added compact, SQL, and facts-by-type artifacts for projections and column usages.
- New scoped facts use lightweight repository-relative evidence references instead of duplicating full SQL snippets per column.
- Projection resolution uses local indexes rather than repeatedly scanning all previously extracted column usages.

## Compatibility

No compatibility adapter is provided. Existing generic column facts and mart lineage remain temporarily available, but scoped projections and column usages are the canonical input for the next lineage migration.
