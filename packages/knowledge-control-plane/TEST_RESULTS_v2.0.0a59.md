# Test results — Analysis UI 2.0.0a59

## Completed

- Knowledge API publication, URL normalization, retry and delayed-response regressions: `6 passed`.
- Independent timeout settings contract: `2 passed`.
- Module baseline and profile discovery: `10 passed`.
- Knowledge API same-origin proxy: `8 passed`.
- Registered analysis artifacts: `6 passed`.
- Selected affected runtime scenarios (OpenAPI boundary, external Knowledge API capability, versioned publication, publication retry, diagnostics): `5 passed`.
- Total unique completed affected tests: `37 passed`.
- `python -m compileall -q src tests`: passed.
- OpenAPI generation/version verification: passed.
- Frontend orchestration/Knowledge API boundary: passed.
- Frontend dependency portability: passed.
- Frontend visual contract: passed.
- Knowledge boundary inventory: passed.
- Source manifest generation and verification: passed.

## Not counted as completed

A combined run of `test_knowledge_api_proxy.py`, `test_analysis_artifacts.py` and `test_runtime_backend.py` printed successful progress but exceeded the tool timeout during the shared HTTP-server teardown. The files were rerun separately; the two short files and five affected runtime tests completed successfully. The full historical `test_runtime_backend.py` suite was not counted as completed.
