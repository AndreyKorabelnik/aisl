# Release notes — code-analyzer-core 0.41.3

Iteration 50 adds semantic inventory for SQL nested inside the datamart DSL and repository-local SQL path references.

## Changes

- SQL keywords inside strings and comments no longer create false nested-SQL signals.
- Added `sql_script_embedded_sql` facts linked to their parent `sql_script_statement`.
- Nested SQL is classified as schema definition/change, data write, script value query, or other SQL.
- Graph-changing nested SQL is explicitly marked, but canonical lineage inclusion remains deferred.
- Added `sql_script_invocation` facts for SQL path references.
- Repository-local paths are resolved by exact path or static suffix after a dynamic prefix.
- Deployment metadata is not modeled; unresolved dynamic paths remain explicit.

## Compatibility

No compatibility layer is provided. The SQL script semantic facts are new canonical evidence types.
