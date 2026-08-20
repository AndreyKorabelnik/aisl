# AISL Publication Bundle Boundary — Test Status

Date: 2026-08-18

## Current targeted verification

Fresh targeted rerun after the final boundary cleanup:

- KCP publication bundle tests
- KCP knowledge execution/bundle semantics
- KCP headless Producer boundary
- Knowledge API publication bundle import
- Knowledge API CLI import surface

Result: **42/42 PASS** (`6.66s`).

## Additional acceptance already completed in this block

- KCP full package regression: `96/96 PASS`.
- Cross-module real KCP bundle builder -> real Knowledge API importer -> Server CAS/revision: PASS.
- Producer output root deliberately absent from Server `allowed_roots`: PASS.
- Tampered bundle rejection: PASS.
- Python compile of changed KCP/API modules: PASS.

## Full Knowledge API regression

Attempted twice in the available sandbox after providing the missing DuckDB test dependency. Both runs exceeded the execution time limit after making progress without an observed failure. The suite is therefore recorded as **PARTIAL/TIMEOUT**, not PASS.

## Non-functional test-environment observations

An earlier KCP run had test-environment contamination from an incomplete `PYTHONPATH`; another exposed a timing-sensitive observability threshold. After correcting the environment and isolated timing retry, the correctly configured KCP full suite completed `96/96 PASS`.
