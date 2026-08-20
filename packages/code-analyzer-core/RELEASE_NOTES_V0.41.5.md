# Release notes — code-analyzer-core 0.41.5

Iteration 52 introduces statement-local SQL SELECT scopes and typed relation references.

## Changes

- Added canonical `sql_select_scope` facts for statement, CTE, derived-query, and set-operation branch scopes.
- Added canonical `sql_relation` facts bound to one concrete SELECT scope.
- Relation references are classified as `physical`, `physical_template`, `cte`, or `derived`.
- CTE references are no longer indistinguishable from physical tables in the new scoped contract.
- Derived relations point to the child SELECT scope that defines them.
- Relation aliases are local to a scope; the same alias can be reused safely in another CTE or derived query.
- INSERT/CREATE targets are excluded from read-relation facts and remain modeled by the existing target contracts.
- Query facts expose `select_scope_ids` without duplicating the full scoped payload.
- Added SQL and compact artifacts plus facts-by-type for scopes and relations.

## Compatibility

No compatibility adapter is provided. Existing unscoped query/source fields remain temporarily available, but the new scoped facts are the canonical basis for the next lineage migration.
