# Test status — iteration 51

## Focused automated tests

- 46 passed, 0 failed.
- Includes semantic placeholder preservation, local `let` binding resolution, schema-template lineage, script splitting and line evidence, SQL mart lineage, schema resolution, source-scope model, table observations, system-description evidence, conceptual data-model evidence, and observation contracts.

## Static checks

- `compileall`: passed.
- Analysis profile/manifest validation through real execution: passed.

## Real repository smoke regression

`datamart_profile_fl`:

- top-level SQL queries: 475
- script statements: 1,866
- script bindings: 815
- semantic placeholders: 915
  - locally bound: 320
  - logical schema templates: 146
  - unbound semantic: 449
- mart column lineage: 3,363
  - evidence confirmed: 401
  - evidence unresolved: 2,962
  - complete: 238
  - partial: 3,125
- source-table usages: 1,294
  - confirmed: 1,093
  - unresolved: 201
- SQL mart lineage gaps: 913

No public query preview contains the synthetic literal `PLACEHOLDER`.

## Known limitations

- Local binding resolution is limited to prior scalar assignments in the same file.
- Cross-file argument flow and dynamic invocation parameters are not yet resolved.
- Dynamic relation/column/expression/predicate placeholders remain gaps.
- CTE and derived-relation aliases are not yet recursively resolved, causing many `source_table_unknown` links.
- JOIN type and scoped JOIN predicate modeling remain unchanged.
- Nested script-value SQL is inventoried but not merged into canonical mart lineage.

## Not run

Full multi-module platform regression was not run for this bounded core-only iteration.
