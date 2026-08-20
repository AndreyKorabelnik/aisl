# Iteration 18 validation results

Date: 2026-07-29
Artifact: `analysis-ui 2.0.0a15`

## Analysis UI regression

Command: `scripts/check.sh`

- baseline verification: PASS — 36 immutable files, 14 intentionally migrated frontend files;
- frontend visual contract: PASS — 12 legacy sections and 14 workspace sections pinned;
- orchestration/knowledge boundary: PASS;
- frontend dependency portability: PASS — 310 public HTTPS resolved URLs, no private `.npmrc` host/auth/TLS override;
- source manifest: PASS — 195 files at test time;
- base/contract/backend regression: **83 passed**;
- isolated runtime regression: **44 passed**;
- total: **127 passed, 0 failed, 0 skipped**.

## UCP compact-source production E2E

- repositories selected: 2;
- repository analyses: **2 completed, 0 failed**;
- runner status: completed;
- workspace Knowledge Layer: completed, 25,178,112 bytes;
- report: completed;
- report contract: 12/12 required headings;
- evidence citations: 16 known, 0 unknown;
- report warnings/errors: 0/0;
- Knowledge API publication: HTTP 201;
- Knowledge API read checks: HTTP 200;
- same-origin proxy: 8/8 routes byte-identical to direct Knowledge API.

Published `Individual` detail:

- field occurrences: 7;
- keys: 1;
- relationships: 4 (`addresses`, `birthDate`, `birthPlace`, `gender`).

## Production frontend build gate

Project-owned package metadata is portable. `npm ci` was nevertheless blocked by the recovery platform's forced npm gateway, which returned HTTP 404 for `vue-tsc@2.2.12`. `npm run build` was therefore not executed and is not claimed as passed.

## Full UCP source gate

The full corporate UCP source archives from the previous chat were not mounted in this recovery runtime. The runner validation used a compact UCP-shaped source replay and is explicitly labelled as such.
