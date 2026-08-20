# Test results — Analysis UI 2.0.0a60

## Completed

- `python -m compileall src` — passed.
- Assistant context, observability, profile, target hand-off and generic OpenAPI contract tests — `28 passed`.
- The new HTTP 422 test confirms that prompt text and response body are absent from logs and API errors.
- Generated OpenAPI document is current.

## Full-suite status

A full 180-test UI run was attempted but did not complete within 120 seconds. It reached the broader suite after the assistant tests; the first observed contract mismatch was the expected stale generated OpenAPI after the version bump. OpenAPI was regenerated and its complete contract test file then passed. The timed-out full run is not reported as successful.

## Frontend

Frontend source, `package.json` and lock file are unchanged. No npm build is required for this iteration.
