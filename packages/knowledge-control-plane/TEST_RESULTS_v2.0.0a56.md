# Test results — Analysis UI 2.0.0a56

## Executed

- Version/dependency/profile integration: `11 passed`.
- `python -m compileall -q src tests`: passed.
- OpenAPI generation: passed.
- Frontend contract checks: passed.
- Source-manifest generation and verification: passed.
- Clean archive smoke verification: passed.
- ZIP integrity and SHA-256 verification: passed.

## Coverage

The integration test verifies that an explicit diagram request sent through the Analysis UI assistant API is retried when the model first returns plain text and completes only after a fenced Mermaid answer is returned.

## Scope

Frontend sources and npm dependencies were not changed. Production frontend rebuild was not required for this iteration.
