# Test status — iteration 56

## Focused automated tests

- 79 passed, 0 failed.
- Added tests for one-scope CTE binding, derived binding, multi-branch CTE UNION, multi-branch derived UNION, nested CTE shadowing, and conservative unique-name fallback when lexical scope traversal is unavailable.
- Existing scoped columns, write-target binding, direct lineage, semantic placeholders, script structure, mart lineage, source-scope, schema, table observation, system description, conceptual model, observation contracts, and version consistency tests remain green.

## Static and package checks

- `compileall`: passed.
- SQL profile execution: passed.
- Runtime/package version consistency: passed.
- Source-tree manifest: passed.
- Clean ZIP extraction and internal-manifest validation: passed.

## Real repository smoke regression

`datamart_profile_fl`:

- files scanned: 480
- SQL units: 306
- SQL queries: 475
- SELECT scopes: 1,164
- scoped relations: 1,426
- CTE relations: 651
- derived relations: 178
- resolved intermediate relations: 829
- unresolved intermediate relations: 0
- intermediate definition branches: 963
- multi-branch intermediate references: 72
- maximum branches on one intermediate reference: 18
- scoped projections: 7,217
- scoped column usages: 10,636
- direct scoped lineage edges: 427
- scoped lineage gaps: 101
- removed scalar `source_scope_id` occurrences in relation facts: 0
- elapsed full repository run: 12.84 seconds
- peak RSS: approximately 649 MiB

## Known limitations

- Recursive CTE/derived field traversal is not yet implemented.
- Wildcard output schemas are not expanded.
- Set-operation field mapping is not yet followed recursively.
- Direct lineage still stops at 245 intermediate CTE/derived origins.
- MERGE/UPDATE assignment lineage is not supported by the scoped contract.
- Final JSONL/KLC ingestion is outside this core-only iteration.

## Not run

Full multi-module platform regression was not run for this bounded core-only iteration.
