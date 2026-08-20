# Test status — iteration 49

## Focused automated tests

- 37 passed, 0 failed.
- Includes new mixed SQL/DSL splitter and classification tests plus existing SQL, schema-resolution and SQL evidence contract tests.

## Real repository smoke regression

`datamart_profile_fl`:

- top-level SQL queries: 475 (previously 2,112 apparent queries)
- separate script statements: 1,866
- nested-SQL script markers: 169
- SQL-path references: 160
- mart column lineage: 190 (unchanged)
- SQL mart lineage gaps: 348 (previously 932)

## Known limitations

- Nested SQL inside DSL assignments/control flow is inventoried but not yet parsed into canonical SQL lineage.
- Two conditional dynamic CREATE statements therefore do not currently contribute to top-level mart inventory.
- JOIN type and scoped column-to-relation resolution are not addressed in this iteration.

## Not run

Full platform regression was not run for this bounded core-only SQL classification change.
