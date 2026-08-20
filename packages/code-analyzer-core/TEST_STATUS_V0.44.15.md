# Test status — code-analyzer-core 0.44.15

## Automated
- SQL regression (`tests/test_sql_*.py`): **147 passed**
- focused scoped/version regression: **39 passed** (subset of the SQL regression plus version consistency)
- `compileall`: **PASS**

## Behavior verified
- duplicate relation aliases no longer abort SQL evidence generation; affected usages remain explicit `ambiguous / ambiguous_alias`.
- relations, projections and join observations remain published conservatively.

## Known limitation
- the ambiguous SQL scope is not guessed or auto-rewritten; lexical source linking is skipped for that scope, so downstream lineage may remain partial as intended.
