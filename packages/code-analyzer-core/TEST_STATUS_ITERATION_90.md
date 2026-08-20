# Test status — iteration 90

## Focused tests

- workflow/config binding tests;
- canonical SQL artifact tests;
- package version consistency.

Result: **9 passed, 0 failed**.

## Real repository smoke

Repository: `datamart_profile_fl`

- status: completed;
- elapsed time: 21.03 seconds;
- canonical SQL artifact: valid;
- workflow bindings: 2,853;
- exact `epk_client` bindings: 6;
- exact `epk_client_v2` bindings: 9;
- portable evidence check: passed.

## Packaging checks

- compileall: passed;
- source-tree manifest: regenerated;
- ZIP integrity: required before delivery;
- clean-extraction focused tests: required before final SHA.

## Deliberately not run

The full core suite was not run. The change is additive and isolated to SQL-relevant configuration extraction and canonical serialization; SQL parsing, lineage construction, database schema analysis and other analyzers were not modified.
