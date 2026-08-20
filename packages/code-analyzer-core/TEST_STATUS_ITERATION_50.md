# Test status — iteration 50

## Focused automated tests

- 41 passed, 0 failed.
- Includes mixed SQL/DSL splitting, nested SQL classification, quoted-text suppression, SQL path resolution, existing SQL lineage and SQL evidence contract tests.

## Real repository smoke regression

`datamart_profile_fl`:

- top-level SQL queries: 475
- script statements: 1,866
- nested SQL facts: 140
- graph-changing nested SQL facts: 8
- SQL path references: 158
- path references resolved repository-locally: 13
- mart column lineage: 190
- SQL mart lineage gaps: 348

## Known limitations

- Dynamic SQL paths using assignments/placeholders are not yet resolved.
- Nested script-value queries are not included in canonical mart lineage.
- Conditional DDL is marked graph-changing but not materialized as mart inventory.
- JOIN type and scoped column-to-relation resolution remain unchanged.

## Not run

Full platform regression was not run for this bounded core-only script semantic inventory change.
