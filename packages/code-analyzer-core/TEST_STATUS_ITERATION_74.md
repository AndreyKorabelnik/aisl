# Test status — iteration 74

## Focused and affected tests

- SQL test suite: 105 passed.
- SQL + physical-model + lightweight CLI affected suite: 112 passed.
- Failures: 0.

## Real repository smoke

Repository: `datamart_profile_fl`

- analysis completed in 18.20 seconds;
- peak RSS: 740,140 KB;
- 11,239 column usages preserved;
- 48 usages resolved by `prior_direct_projection_alias`;
- `ambiguous_unqualified`: 365 -> 317;
- source-field resolution: 0.966820 -> 0.971160;
- recursive partial paths: 176 -> 140;
- scoped lineage gaps: 219 -> 183;
- canonical SQL content fingerprint: `d7de0f0247b2921bcaf59ba3ee41b6e871c155cc6416fe225f04e1981edd42fb`.

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
- affected tests from clean extraction: 112 passed;
- real-artifact validation report: present and verified.
