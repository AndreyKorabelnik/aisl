# Test status — iteration 80

## Focused and affected tests

- New materialized-relation contract tests: 8 passed.
- Complete SQL and package-version affected suite: 138 passed.
- Failures: 0.

## Real repository smoke

Repository: `datamart_profile_fl`

- analysis completed in 19.69 seconds;
- peak RSS: 742,592 KB;
- 11,239 column usages preserved;
- 38 additional usages resolved;
- `ambiguous_unqualified`: 243 -> 205;
- source-field resolution: 0.977850 -> 0.981286;
- partial recursive lineage: 140 -> 29;
- total lineage gaps: 183 -> 72;
- canonical SQL content fingerprint: `a648117b58b079db783bd4fa9519883591eb80a0a8f16769b815c66dc88ac6c8`.

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
- affected tests from clean extraction: 138 passed;
- real-artifact fingerprint reproduced from clean extraction.
