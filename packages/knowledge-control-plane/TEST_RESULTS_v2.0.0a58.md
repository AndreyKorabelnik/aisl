# Test results — Analysis UI 2.0.0a58

## Executed

- Assistant/API integration and module contracts: `31 passed`.
- Dedicated assistant-context/profile/observability group: `19 passed`.
- Full HTTP recovery scenario from `invalid_arguments`: passed (`200 OK`, two model calls, rejected call logged separately from successful Knowledge API calls).
- `python -m compileall -q src tests`: passed.
- OpenAPI version verification: passed.
- Frontend orchestration boundary: passed.
- Frontend dependency portability: passed.
- Frontend visual contract: passed.
- Knowledge boundary inventory: passed.
- Source manifest verification: passed.
- Clean archive smoke verification: passed.
