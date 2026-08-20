# Test results — Analysis UI 2.0.0a47

## Scope

Focused validation for:

- priority master filtering;
- canonical profiles in the attribute-addition wizard;
- PDM input without a separate static-analysis profile;
- UI-supplied ephemeral Bitbucket credentials;
- non-interactive checkout and visible checkout failures.

## Results

- Python compileall: passed.
- Focused feature/runtime regression: 25 passed.
- Generic API, frontend migration and module baseline: 25 passed.
- Frontend orchestration/knowledge API boundary: passed.
- Frontend dependency portability: passed.
- Frontend visual contract: passed.
- Source manifest: 298 files, verified.

## Not run

The full historical test suite was intentionally not run. The user requested only necessary tests, and the focused suites cover all changed paths. Production frontend build was not repeated because no dependency graph changes were made and the previous environment could not fetch `vue-tsc` from the internal npm gateway.

## Known pre-existing issue

Some historical pipeline tests still expect repository-target execution for profiles that are now workspace-only. They are unrelated to this change and were not treated as regressions.
