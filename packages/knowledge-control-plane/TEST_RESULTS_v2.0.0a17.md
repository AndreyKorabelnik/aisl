# analysis-ui 2.0.0a17 validation

- Base/backend/contract tests: **87 passed**.
- Runtime tests: **48 passed** in bounded groups/isolated processes because TestClient/subprocess teardown can stall in one long process.
- Frontend typed-contract verification: PASS.
- Frontend visual contract: PASS.
- Dependency portability: PASS.
- Production Vite build remains externally blocked when the configured npm gateway does not provide `vue-tsc@2.2.12`.
