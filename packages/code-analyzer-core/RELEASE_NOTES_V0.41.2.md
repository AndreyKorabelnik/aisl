# Release notes — code-analyzer-core 0.41.2

Iteration 49 introduces the first bounded SQL-vitrine improvement: mixed SQL/DSL script classification.

## Changes

- Added a lexical semicolon splitter that respects strings, comments and dollar-quoted blocks.
- Added deterministic top-level classification of SQL versus DSL/script fragments.
- DSL assignments, control flow, logging, invocations and error-handling statements are no longer published as SQL queries.
- Added `sql_script_statement` facts with repository-relative evidence, referenced SQL paths and nested-SQL markers.
- Added SQL profile counts for script statements and statements containing nested SQL.
- Added `sql_script_structure_scan` to the SQL mart profile.

## Compatibility

No compatibility adapter is provided. Consumers of the SQL profile should use `sql_script_statement` for DSL inventory and `sql_query` only for top-level SQL.
