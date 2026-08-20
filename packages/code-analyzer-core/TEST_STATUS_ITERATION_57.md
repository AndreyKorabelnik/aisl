# Test status — iteration 57

## Focused automated tests

- 88 passed, 0 failed.
- Added tests for:
  - one-level CTE transformation;
  - multi-level CTE traversal;
  - every UNION branch with ordinal correspondence and different aliases;
  - terminal expression inside a CTE;
  - cycle detection;
  - maximum depth enforcement;
  - safe single-source `*` passthrough;
  - safe qualified `alias.*` passthrough;
  - ambiguous multi-source wildcard preservation as partial.
- Existing scoped relations, columns, write targets, direct lineage, placeholders, scripts, legacy mart lineage, source scope, schema, table observation, system description, conceptual model, observation contracts, and version consistency tests remain green.

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
- direct scoped lineage edges: 427
- recursive terminal paths: 731
- confirmed paths: 25
- inferred-target paths: 530
- partial paths: 176
- physical/template source paths: 484
- terminal expressions/parameters: 71
- recursive gaps: 116
- ambiguous-source recursive gaps: 111
- unresolved intermediate-projection gaps: 4
- unsafe wildcard gaps: 1
- maximum recursion depth observed: 8
- unique recursive path IDs: 731 of 731
- unique total scoped gap IDs: 217 of 217
- elapsed full repository run: 12.91 seconds
- peak RSS: approximately 660 MiB

## Known limitations

- Cross-file materialized intermediate tables are not traversed.
- Full wildcard schema expansion is unavailable.
- Ambiguous unqualified columns are intentionally not guessed.
- Row filters and JOIN context are not yet embedded in recursive field paths.
- MERGE/UPDATE assignments remain outside the scoped lineage contract.
- Final JSONL/KLC ingestion is outside this core-only iteration.

## Not run

Full multi-module platform regression was not run for this bounded core-only iteration.
