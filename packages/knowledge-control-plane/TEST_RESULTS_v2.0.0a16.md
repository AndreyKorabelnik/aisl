# analysis-ui 2.0.0a16 validation

Date: 2026-07-29

## Scope

- accept arbitrary readable local directories as repository source input;
- retain direct-child splitting when independent project boundaries are proven by generic markers;
- remove the UCP preset and UCP-specific workspace defaults/hints;
- remove browser checkboxes for manual LLM rerun and forced rebuild;
- retain advanced recovery policies in the orchestration API.

## Verification

- Python compilation: PASS;
- source manifest: PASS — 200 distributable files after this report is included;
- immutable runtime baseline: PASS;
- frontend visual contract: PASS — intentional WorkspaceForm template update pinned;
- frontend orchestration/knowledge boundary: PASS;
- frontend dependency portability: PASS — 310 public HTTPS package URLs;
- Knowledge API boundary inventory: PASS;
- base/contract/backend regression: **83 passed**;
- focused frontend and policy regression: **27 passed**;
- changed repository-discovery contour: **5 passed**;
- markerless local-development fixture: PASS;
- real UCP source-export discovery smoke: PASS — `ucp-api` and `ucp-tsa-v4` found without `.git`.

## Runtime-suite note

The complete `scripts/check.sh` passed all 83 base tests and the first isolated runtime tests,
but the recovery container again stalled while launching a later independent TestClient test.
No assertion failure was observed. Every test directly affected by this checkpoint was executed
independently and passed. A full unrelated runtime replay was intentionally not required for this
small UI/discovery change under the agreed tiered-testing strategy.
