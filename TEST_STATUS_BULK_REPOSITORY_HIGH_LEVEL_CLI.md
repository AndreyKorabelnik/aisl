# Test Status — Bulk Repository High-Level CLI

Date: 2026-08-14

## PASS

- High-level KCP batch + one-shot compatibility targeted tests: **19/19 PASS**.
- Unchanged Runner repository-batch/acquisition/CLI targeted tests: **12/12 PASS**.
- End-to-end CLI routing smoke with a fake Runner process: **PASS**.
- Full local one-command smoke with real Runner → temporary git clone → Core → KLC on two repositories: **2/2 PASS**.
  - user command contains only scenario/project/optional limit;
  - Control Plane resolves `repository-inventory-v1`;
  - temporary profile is `knowledge_profile/v2` with repository scope;
  - pinned catalogs are supplied internally;
  - no `--system-id` is required for batch;
  - temporary Control-Plane profile directory is empty after completion;
  - returned summary preserves `max_concurrent_checkouts=1` and `persistent_repository_checkout_count=0`.
- `compileall` for Knowledge Control Plane: PASS.
- imports/version/runtime-contract discovery: PASS (`knowledge-control-plane 1.2.0a17`).
- CLI help exposes `--bitbucket-project-url` and `--repository-limit`: PASS.

## Full Knowledge Control Plane suite

Attempted: **109 PASS, 5 FAIL**.

The five failures are pre-existing stale string-count assertions in `tests/test_knowledge_execution_ui.py`. They count occurrences of the substring `--repository`; the current canonical command also contains one `--repository-metadata-json` per repository, so each assertion double-counts. The same five failures were reproduced on the untouched input canonical before this high-level CLI change. They are not claimed as PASS and were not modified as part of this task.

## Not run

Corporate live Bitbucket Data Center acceptance is not possible in this environment because no real project endpoint/credentials were supplied. A local Bitbucket-compatible HTTP + git acceptance passed 2/2; the corporate endpoint is the next step on the user's machine.
