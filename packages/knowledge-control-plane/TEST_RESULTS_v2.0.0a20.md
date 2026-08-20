# Test results — analysis-ui 2.0.0a20

- Source/runtime compilation: PASS.
- Source manifest verification: PASS (177 files).
- Frontend visual contract: PASS (12 preserved sections, 14 workspace sections).
- Frontend orchestration/Knowledge API boundary: PASS.
- Frontend dependency portability: PASS.
- Knowledge ownership boundary audit: PASS.
- Base/backend-independent/contract tests: 38 passed.
- Supported runtime tests: 50 passed in five isolated groups of 10.
- Removed backend audit: PASS; no `backend/` directory and no `analysis_ui.backend`, `backend.main` or route-migration metadata.
