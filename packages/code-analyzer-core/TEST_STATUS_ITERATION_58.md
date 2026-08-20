# Test status — iteration 58

## Focused and adjacent automated tests

- 115 passed, 0 failed.
- Added 11 scoped JOIN tests covering:
  - LEFT JOIN with equality key and additional predicate;
  - range/temporal column joins;
  - `USING` with one left relation;
  - `USING` after a composite left rowset;
  - CROSS JOIN;
  - chained JOIN side resolution;
  - CTE-to-physical logical JOIN;
  - ambiguous unqualified predicate preservation;
  - reversed predicate operand canonicalization;
  - same-relation additional predicates;
  - transformed multi-column expression links.
- Existing script structure, semantic placeholders, scoped relations, columns, target binding, direct lineage, recursive lineage, mart lineage, source-scope, schema, table-observation, system-description, conceptual-model, observation-contract, universal-source-observation, and version tests remain green.

## Static and package checks

- `compileall`: passed.
- SQL profile execution: passed.
- Runtime/package version consistency: passed.
- Source-tree manifest: passed.
- Clean ZIP extraction and internal-manifest validation: passed.
- Focused tests from clean ZIP extraction: 15 passed.

## Real repository smoke regression

`datamart_profile_fl`:

- files scanned: 480;
- SQL units: 306;
- SQL queries: 475;
- scoped JOIN edges: 292;
- unique JOIN IDs: 292 of 292;
- JOIN types: 238 left, 53 inner, 1 left anti, 0 unknown;
- confirmed JOIN edges: 282;
- partial JOIN edges: 10;
- physical/physical-template JOINs confirmed: 109;
- simple column pairs: 372;
- expression links: 2;
- equality relationships: 310;
- range/temporal relationships: 64;
- additional predicates: 35;
- source-key candidates derived from canonical JOINs: 724;
- legacy `source_join_evidence` files/facts: 0;
- SELECT scopes: 1,164;
- scoped relations: 1,426;
- scoped column usages: 10,636;
- scoped projections: 7,217;
- direct lineage edges: 427;
- recursive terminal paths: 731;
- scoped lineage gaps: 217;
- elapsed full repository run: 12.78 seconds;
- peak RSS: approximately 659 MiB.

## Known limitations

- Ten real JOINs remain partial because an unqualified predicate field has several relation candidates.
- Schema-assisted disambiguation is intentionally not performed.
- Multi-left `USING` cannot name one physical base relation without schema evidence.
- JSONL compact artifact and KLC ingestion are outside this bounded core iteration.

## Not run

The full multi-module platform regression was not run for this core-only iteration.
