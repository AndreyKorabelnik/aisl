# Test status — iteration 67

## Necessary automated tests

- SQL-focused regression: 95 passed, 0 failed.
- New tests cover:
  - SELECT-prefix hint/projection-fragment placeholders;
  - whole select-list placeholders before `FROM`;
  - complete relation extraction after the placeholder;
  - semantic placeholder role preservation;
  - lexical/scoped source coverage calculation.
- `compileall`: passed.

## Real repository validation

`datamart_profile_fl` full SQL analysis:

- elapsed: 17.16 seconds;
- peak RSS: approximately 723 MiB;
- canonical records: 28,619;
- producer: code-analyzer-core 0.42.4 / SQL profile 1.5;
- content fingerprint: `5cda86c6634bec563663030f91d90e8a8331f93049ff3becb2fb1fd94c2abff6`.

Unchanged SQL Source Inventory fixture:

- relation precision: 1.0000;
- relation recall: 1.0000;
- classification accuracy: 1.0000;
- field precision: 1.0000;
- field recall: 1.0000;
- field-role accuracy: 1.0000;
- column resolution rate: 0.9474;
- passed cases: 30 / 30.

Additional parser coverage diagnostics:

- 2 localized `scoped_ast_source_coverage_incomplete` gaps;
- both concern qualified/template dictionary candidates in two staging SQL files;
- no fallback relation facts were fabricated.

## Not run

The full multi-module platform regression was not run. KLC ingestion and the quality evaluator were exercised on the complete real artifact, which is the affected downstream path.
