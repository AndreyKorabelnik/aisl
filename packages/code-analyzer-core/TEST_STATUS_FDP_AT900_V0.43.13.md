# Test status — code-analyzer-core 0.43.13

## Automated tests

- focused full-profile custom DAO update regression: passed;
- FDP / persistence affected suite: **73 passed**;
- `compileall`: passed;
- source manifest verification: passed;
- ZIP integrity verification: passed.

## Fresh AT900 full suite

Repository: `AT900 client-profile`, 1038 files.

- foundation: completed, 21.520 s;
- `flow-lineage`: completed, 35.580 s;
- `persistence-lineage`: completed, 18.039 s;
- timeouts: 0;
- stack dump requests: 0.

The run used `code-analyzer-core 0.43.13` and a new output directory. Earlier analysis outputs were not reused.
