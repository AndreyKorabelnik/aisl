# Test status — iteration 69

## Necessary automated tests

- SQL-focused regression: 102 passed, 0 failed.
- New tests cover:
  - semantic parameters excluded from source-field failures;
  - generated LATERAL/EXPLODE values excluded from source-field failures;
  - real unqualified ambiguity retained as partial coverage.
- `compileall`: passed.

## Real repository validation

`datamart_profile_fl` full SQL analysis:

- elapsed: 18.91 seconds;
- peak RSS: approximately 722 MiB;
- producer: code-analyzer-core 0.42.6 / SQL profile 1.7;
- content fingerprint: `648bc8e3540ddfcaab0119d5284667cec5ef442cc3c32bb8afb84dc68d03932f`;
- source-field resolution rate: 0.966820.

Unchanged SQL Source Inventory fixture:

- relation precision/recall: 1.0000 / 1.0000;
- classification accuracy: 1.0000;
- field precision/recall/role accuracy: 1.0000;
- passed cases: 30 / 30.

## Not run

The full multi-module platform regression was not run. The canonical SQL artifact, KLC ingestion, real repository build, and unchanged quality fixture were tested because they are the affected path.
