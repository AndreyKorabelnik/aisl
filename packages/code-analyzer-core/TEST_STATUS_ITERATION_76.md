# Test status — iteration 76

## Focused and affected tests

- New wildcard-contract tests: 8 passed.
- Complete SQL and package-version affected suite: 121 passed.
- Failures: 0.

## Real repository smoke

Repository: `datamart_profile_fl`

- analysis completed in 18.49 seconds;
- peak RSS: 740,192 KB;
- 11,239 column usages preserved;
- 236 intermediate relations gained complete wildcard contracts;
- 14 additional usages resolved;
- `ambiguous_unqualified`: 263 -> 249;
- source-field resolution: 0.976042 -> 0.977308;
- canonical SQL content fingerprint: `364bc637a38465f4905cbfc0fd78428673fe468d1cfa8a4f954981e5da872a05`.

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
- affected tests from clean extraction: 121 passed;
- real-artifact fingerprint reproduced from clean extraction.
