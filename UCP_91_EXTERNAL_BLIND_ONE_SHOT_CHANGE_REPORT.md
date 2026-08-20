# Change report — UCP 91 external blind one-shot runner

Date: 2026-08-15

## Runtime package changes

None.

No Core, Runner, KLC, Prepared Runtime, Knowledge API, Knowledge Integration, Knowledge Control Plane or AISL contract runtime code changed. Package versions remain unchanged.

## Validation/consumer changes

- Added `run_blind_once.py`, a Gold-isolated one-command orchestration wrapper.
- The wrapper performs publication, API lifecycle, external agent execution, structural validation, freeze and portable result bundling.
- Added compatibility with both `LLM_BASE_URL`/`LLM_MODEL` and `LLM_ENDPOINT`/`LLM_DEFAULT_MODEL` environment naming.
- Added fail-fast validation for missing endpoint/model and incomplete/unreadable mTLS paths.
- Added endpoint sanitization and boolean-only auth metadata so secrets are not persisted.
- Added process-group cleanup for the temporary local Knowledge API.
- Added orchestration-only mock E2E acceptance; the mock result is explicitly excluded from quality scoring.

## Deliberately not implemented

- no LLM reasoning inside AISL;
- no Gold access from the runner;
- no synthetic recall/precision claim;
- no automatic post-Gold tuning;
- no vector/embedding service in AISL;
- no runtime version bump for validation-only tooling.
