# Test results — Analysis UI 2.0.0a52

## Scope

Проверены только контуры, затронутые удалением Bitbucket credentials из frontend/API и переходом на server-environment-only checkout.

## Results

### Authentication, checkout, API and frontend

- Server environment checkout and noninteractive fallback.
- Repository discovery API rejects request-level auth.
- Embedded credentials in URL remain rejected without secret echo.
- API/database secret non-persistence.
- CLI preview redacts server token and does not create helper as a side effect.
- Inherited VS Code `GIT_ASKPASS` is disabled.
- Frontend preparation contains no username/password/token fields.
- Runtime diagnostics expose only presence flags, never values.
- Generic API, module baseline and assistant-context frontend contracts.

Result: **31 passed**.

### Adjacent frontend and observability contracts

- Frontend generic migration.
- Revision-first UI.
- Process observability and log classification.

Result: **21 passed**.

Total affected tests: **52 passed**.

## Additional validation

- Python `compileall`: passed.
- Generic OpenAPI regenerated for `2.0.0a52`; request-level auth schema absent.
- Frontend orchestration/API boundary: passed.
- Frontend dependency portability: passed.
- Frontend visual contract: passed.
- Knowledge API boundary inventory: passed.
- Source manifest generation and verification: passed during packaging.

## Not run

The full historical regression suite and production frontend build were not run because the change is localized and frontend dependencies were not changed.
