# Test results 2.0.0a45 — data model master

## Confirmed

- Focused backend and revision-first UI tests: 15 passed.
- Real Analysis UI E2E with runner 0.9.29 and one Java repository: succeeded.
  - fixed suite: `data-model`;
  - required capabilities: `suite.data-model`, `common.data-model`;
  - fixed report: `data-model-report/v1`;
  - revision `revision-1` and standard chat context created;
  - 274 artifacts registered;
  - all pipeline stages succeeded or were intentionally skipped;
  - persisted welcome messages: 0.
- Repository target is rejected as `workspace_required`.
- No analysis-profile fallback is accepted.
- Python compileall, OpenAPI, frontend boundary and dependency portability: passed.
- TypeScript/Vue syntax, source manifest and ZIP integrity: passed.

## Known limitations

- E2E reporting used a deterministic response file; full LLM rendering quality was not evaluated.
- Production frontend build was not run because the npm dependency set is incomplete.
- No Core, Knowledge Layer or reporting algorithm was changed in this release.
