# Test status — iteration 52

## Focused automated tests

- 50 passed, 0 failed.
- Added tests for CTE-versus-physical classification, derived relation linkage, physical templates, and alias reuse across independent scopes.
- Existing semantic-placeholder, script structure, mart lineage, schema resolution, source-scope, table observation, system-description, conceptual data-model, and observation-contract tests remain green.

## Static checks

- `compileall`: passed.
- Real profile execution and artifact writing: passed.

## Real repository smoke regression

`datamart_profile_fl`:

- SQL queries: 475
- SELECT scopes: 1,164
- scoped relations: 1,426
- physical relations: 187
- physical-template relations: 410
- CTE references: 651
- derived relations: 178
- derived relations without child scope: 0
- duplicate aliases inside one scope: 0
- existing mart-column lineage: 3,363, unchanged by this iteration

## Known limitations

- Projections and column references are not yet bound to scope IDs.
- Existing mart lineage still aggregates projections across nested SELECTs.
- CTE-to-base-table recursive column traversal is not yet implemented.
- Root UNION branches currently have no synthetic set-operation parent scope.
- Scope evidence points to the containing SQL statement; exact AST token offsets are not yet available.
- JOIN type and predicate structure remain on the existing extraction path.

## Not run

Full multi-module platform regression was not run for this bounded core-only scoped inventory change.
