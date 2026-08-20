# Test results — analysis-ui 2.0.0a23

- Full module suite: **93 passed in 85.34 seconds** in one ordinary pytest process.
- Base/contract/profile/store lifecycle: **39 passed**.
- Runtime backend: **50 passed in 71.62 seconds** in one process.
- SQLite file descriptors remained stable after each runtime test; previous growth to hundreds of open handles is eliminated.
- No `os._exit()` wrapper and no per-test interpreter isolation are used.
- Frontend visual, API contract, dependency portability, knowledge-boundary, source manifest and compile checks: PASS.
