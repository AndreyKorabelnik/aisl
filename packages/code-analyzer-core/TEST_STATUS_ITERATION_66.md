# Test status — iteration 66

## Necessary automated tests

- SQL-focused regression: 92 passed, 0 failed.
- New cases cover:
  - line and block comments outside literals;
  - `--` and `/*...*/` inside strings and quoted identifiers;
  - dollar-quoted text;
  - stable newline/offset preservation;
  - scoped relation and filter-column extraction from a statement containing the literal `'--'`.
- `compileall`: passed.

## Real repository validation

`datamart_profile_fl` full SQL analysis:

- elapsed: 15.86 seconds;
- peak RSS: approximately 668 MiB;
- canonical records: 27,883;
- producer: code-analyzer-core 0.42.3 / SQL profile 1.4;
- content fingerprint: `dac08f596f373a232dc9c8d6ba799d1a72a157e493be9a4a5282931aa04550b9`.

The unchanged quality fixture reports:

- relation precision: 1.0000;
- relation recall: 0.9080;
- classification accuracy: 1.0000;
- field precision: 1.0000;
- field recall: 1.0000;
- field-role accuracy: 1.0000;
- column resolution rate on selected files: 0.9421;
- passed cases: 29 / 30.

## Not run

The full multi-module platform regression was not run. The external contract is unchanged and this iteration only modifies SQL lexical normalization.
