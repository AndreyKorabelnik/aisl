# knowledge-api 0.13.1

Iteration 88: publish existing field storage evidence through table detail.

## Changes

- Extended the existing `TableField` response; no new endpoint was introduced.
- Added exact storage observations:
  - physical field name;
  - converter object alias;
  - observed value expression;
  - converter owner/method;
  - deterministic match basis and non-semantic value status;
  - portable evidence references.
- Updated the canonical OpenAPI document.
- Raised the KLC minimum dependency to 0.52.4.

## Validation

- compileall: passed
- focused API/contract tests: 28 passed
- real HTTP smoke on published UCP: passed
- existing Knowledge Assistant `get_source_data_model_table` smoke: passed
- full test suite: not run; publication, administration and unrelated APIs were unchanged
