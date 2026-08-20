# Test status — iteration 54

## Focused automated tests

- 62 passed, 0 failed.
- Added tests for explicit INSERT columns, inferred INSERT mappings, CTAS schema mapping, UNION branch mapping, projection-count mismatch, and DDL-without-source handling.
- Existing scoped columns/relations, semantic placeholders, script structure, mart lineage, schema, source-scope, table-observation, system-description, conceptual-model, and observation-contract tests remain green.

## Static checks

- `compileall`: passed.
- Real profile execution and new artifact writers: passed.

## Real repository smoke regression

`datamart_profile_fl`:

- write targets: 182
- CREATE TABLE: 110
- INSERT: 69
- INSERT OVERWRITE: 3
- no-select-source targets: 111
- inferred INSERT targets: 67
- confirmed create-output-schema targets: 4
- target-projection bindings: 402
- confirmed bindings: 22
- inferred bindings: 339
- unresolved wildcard bindings: 41
- arity mismatches: 0
- elapsed real-repository run: 12.33 seconds
- peak RSS: approximately 646 MiB

## Known limitations

- INSERT mappings without explicit target columns remain inferred until target schema evidence is joined.
- Wildcards are not expanded.
- Direct target bindings do not yet traverse CTE or derived-relation columns to physical sources.
- MERGE/UPDATE target assignments are not yet represented by this projection-binding contract.
- Existing legacy mart-column lineage is still present and has not yet switched to scoped facts.
- The final JSONL/KLC ingestion contract is not part of this iteration.

## Not run

Full multi-module platform regression was not run for this bounded core-only iteration.
