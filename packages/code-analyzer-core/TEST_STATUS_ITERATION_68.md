# Test status — iteration 68

## Necessary automated tests

- SQL-focused regression: 100 passed, 0 failed.
- New tests cover:
  - LATERAL VIEW generated relations;
  - chained generated aliases;
  - unqualified generated outputs versus physical fields;
  - nested CTE field paths;
  - nested fields on a sole physical relation;
  - preservation of ambiguity with multiple sources.
- `compileall`: passed.

## Real repository validation

`datamart_profile_fl` full SQL analysis:

- elapsed: 16.29 seconds;
- peak RSS: approximately 722 MiB;
- canonical records: 28,627;
- producer: code-analyzer-core 0.42.5 / SQL profile 1.6;
- content fingerprint: `87b79a8213b9b6f93535d1a025e14b5933e1861e0b677386b6efe8f9a7619510`.

Column resolution:

- total usages: 11,239;
- resolved usages: 10,721;
- alias-unresolved usages: 0;
- generated-relation usages: 27;
- ambiguous unqualified usages: 365;
- semantic parameters: 151;
- relation-unavailable usages: 2.

Unchanged SQL Source Inventory fixture:

- relation precision/recall: 1.0000 / 1.0000;
- classification accuracy: 1.0000;
- field precision/recall/role accuracy: 1.0000;
- column resolution rate: 0.9508;
- passed cases: 30 / 30.

## Not run

The full multi-module platform regression was not run. The affected SQL core tests, full real-repository analysis, KLC ingestion, and unchanged quality fixture were run.
