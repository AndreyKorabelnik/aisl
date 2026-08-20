# Test results — Analysis UI 2.0.0a51

## Scope

Проведены только проверки, затронутые переводом стандартных мастеров на однорепозиторный режим, сохранением специальных workspace-сценариев, API/frontend-контрактами и упаковкой артефакта.

## Results

### Runtime routing and execution

- Standard one-repository masters, backend target validation, interaction workspace, retries, caching and prepared knowledge contexts: **17 passed**.

### API and frontend contracts

- Profile discovery: **6 passed**.
- Revision-first UI: **10 passed**.
- Frontend generic migration: **9 passed**.
- Generic API contract: **12 passed**.
- Module baseline: **4 passed**.
- Assistant-context frontend contract: **7 passed**.
- Knowledge API publication: **3 passed**.

Total independently completed affected tests: **68 passed**.

## Additional validation

- Python `compileall`: passed.
- Frontend orchestration/API boundary: passed.
- Frontend dependency portability: passed.
- Frontend visual contract: passed.
- Knowledge API boundary inventory: passed.
- OpenAPI contract regenerated for `2.0.0a51`.
- Source manifest generation and verification: passed during packaging.
- Clean ZIP extraction: source manifest passed; focused runtime/frontend verification: **23 passed**.

## Not run

The full historical regression suite was not run because the change is localized and the user requested only necessary testing.

The production frontend build was not run in the packaging environment because `frontend/node_modules` is not distributed. No frontend dependencies were added. In the target environment run `npm ci --include=dev && npm run build`.
