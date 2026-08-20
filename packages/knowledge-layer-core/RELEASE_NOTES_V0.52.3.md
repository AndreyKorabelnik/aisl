# knowledge-layer-core 0.52.3

## Added

- Added `KnowledgeLayerQuery.list_sql_target_column_lineage()`.
- Added capability `common.sql-target-column-lineage` to SQL knowledge-layer manifests.
- Added `sql-target-column-lineage/v1`, a deterministic read-only projection over the
  existing `sql_recursive_column_lineage` and `sql_scoped_lineage_gap` tables.

## Contract behavior

- Target relation and target column filters are exact; no fuzzy or semantic matching is used.
- Every recursive terminal branch remains a separate result item.
- Ordered branch and transformation paths, evidence, recursive resolution, physical origin
  and lineage status are preserved.
- Related lineage gaps are returned separately with complete counts and explicit truncation.
- No new SQL facts, tables, lineage algorithms or core-analysis behavior were introduced.

## Packaging

- Version advanced to 0.52.3, satisfying the existing `knowledge-reporting >=0.52.3`
  dependency boundary.

## Known limitations

- Recursive lineage remains statement-local according to the existing core contract.
- Cross-file temporary-table composition is not added by this release.
- JOIN/filter row-selection context is not attached to recursive paths by this query.
