# knowledge-api 0.28.0 test status

Status: PASS

- Final full Knowledge API suite: **74 passed**.
- Focused effective-model/lineage/storage behavior tests remained unchanged after moving schema reads to KLC.
- Structural boundary tests prevent direct DuckDB/KLC-mart SQL from returning to Knowledge API.
- OpenAPI snapshot regenerated for 0.28.0 and verified by the full suite.
- Compileall: PASS.
- Package manifest/integrity checks: recorded after ZIP verification.

The Knowledge API-owned SQLite publication registry remains intentionally local to Knowledge API and is not a KLC mart read path.
