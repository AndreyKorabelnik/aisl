# Test status — iteration 55

## Focused automated tests

- 75 passed, 0 failed.
- Added tests for confirmed direct physical lineage, CTE stopping boundary, inferred INSERT target mapping, ambiguous source gaps, wildcard target gaps, expressions without source columns, and semantic parameters that must not bind to tables, multi-input expressions, logical physical templates, partial target mappings, and explicit wildcard mappings.
- Existing write-target, scoped-column/relation, placeholder, script, legacy lineage, schema, source-scope, table-observation, system-description, conceptual-model, and observation-contract tests remain green.

## Static checks

- `compileall`: passed.
- Real profile execution and new lineage/gap artifact writers: passed.

## Real repository smoke regression

`datamart_profile_fl`:

- scoped direct lineage edges: 427
- confirmed direct: 22
- inferred target: 345
- partial: 60
- intermediate CTE/derived origins: 245
- logical physical-template origins: 60
- expression/parameter origins: 62
- unresolved origins: 60
- semantic-parameter edges: 24
- semantic-parameter edges with false relation: 0
- scoped lineage gaps: 101
- unique target fields: 231
- legacy mart-column lineage edges retained for comparison: 3,363
- elapsed real-repository run: 13.05 seconds
- peak RSS: approximately 648 MiB

## Known limitations

- CTE and derived fields are not yet recursively resolved to base physical columns.
- INSERT target fields without an explicit column list remain inferred.
- Wildcards are not expanded.
- 60 unqualified source usages with multiple candidate relations remain ambiguous by design.
- Filters affecting row inclusion are separate scoped usages and are not yet attached to field explanation packs.
- MERGE/UPDATE assignment lineage is not yet supported by the scoped direct contract.
- Legacy mart lineage remains present but is non-canonical.
- Final JSONL/KLC ingestion is not part of this iteration.

## Not run

Full multi-module platform regression was not run for this bounded core-only iteration.
