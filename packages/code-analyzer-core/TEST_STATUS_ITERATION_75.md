# Test status — iteration 75

## Focused and affected tests

- New output-contract tests: 7 passed.
- Complete SQL and package-version affected suite: 113 passed.
- Failures: 0.

## Real repository smoke

Repository: `datamart_profile_fl`

- analysis completed in 18.58 seconds;
- peak RSS: 739,304 KB;
- 11,239 column usages preserved;
- 54 usages resolved by `unique_complete_intermediate_output_contract`;
- `ambiguous_unqualified`: 317 -> 263;
- source-field resolution: 0.971160 -> 0.976042;
- canonical SQL content fingerprint: `61ca6816f5af4b19c65e0603b71ed786fe75b8437cf5fb703b3a344c84f48ec5`.

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
- affected tests from clean extraction: 113 passed;
- real-artifact fingerprint reproduced from clean extraction.
