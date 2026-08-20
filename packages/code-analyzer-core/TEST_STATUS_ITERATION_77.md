# Test status — iteration 77

## Focused and affected tests

- New set-operation tests: 9 passed.
- Complete SQL and package-version affected suite: 130 passed.
- Failures: 0.

## Real repository smoke

Repository: `datamart_profile_fl`

- analysis completed in 19.12 seconds;
- peak RSS: 740,052 KB;
- 11,239 column usages preserved;
- 72 complete set-operation relation contracts;
- one partial set-operation relation contract;
- six additional usages resolved;
- `ambiguous_unqualified`: 249 -> 243;
- source-field resolution: 0.977308 -> 0.977850;
- canonical SQL content fingerprint: `186f05e4b13ca9c7293fc649edf723c7be77b3fdb507cbbb1a070c1167ac0a14`.

## Curated quality baseline

- cases: 30/30 passed;
- relation precision/recall: 1.0000 / 1.0000;
- classification accuracy: 1.0000;
- field precision/recall: 1.0000 / 1.0000;
- field-role accuracy: 1.0000.

## Packaging checks

Final ZIP verification criteria:

- compileall: passed;
- source-tree manifest: passed;
- ZIP integrity: passed;
- affected tests from clean extraction: 130 passed;
- real-artifact fingerprint reproduced from clean extraction.
