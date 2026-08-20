# Test status — iteration 53

## Focused automated tests

- 54 passed, 0 failed.
- Added tests for semantic usage roles, relation binding, scope-local projection sources, ambiguous unqualified columns, single-relation inference, and output-alias handling.
- Existing scoped relation, placeholder, script, mart-lineage, schema, source-scope, table-observation, system-description, conceptual-model, and observation-contract tests remain green.

## Static checks

- `compileall`: passed.
- Real profile execution and all new artifact writers: passed.

## Real repository smoke regression

`datamart_profile_fl`:

- SQL queries: 475
- SELECT scopes: 1,164
- scoped relations: 1,426
- scoped projections: 7,217
- scoped column usages: 10,636
- resolved column usages: 10,137
- ambiguous column usages: 383
- unresolved column usages: 116
- relation-resolution coverage: 95.3%
- physical/template relations with resolved fields: 283
- distinct used relation/field pairs: 2,050
- existing mart-column lineage: 3,363, intentionally unchanged
- elapsed real-repository run: 12.61 seconds
- peak RSS: approximately 643 MiB

## Known limitations

- Target INSERT/CREATE column binding has not yet migrated to scoped projections.
- CTE and derived relation usages resolve to the intermediate relation, not yet recursively to physical base columns.
- Wildcard projections are identified but not expanded without schema evidence.
- 383 unqualified usages with multiple in-scope relations remain ambiguous by design.
- 95 alias references and 21 relation-free usages remain unresolved on the real repository.
- JOIN type and structured predicate extraction are not yet migrated to the scoped AST.
- The generated JSON is still not the final streaming JSONL contract.

## Not run

Full multi-module platform regression was not run for this bounded core-only iteration.
