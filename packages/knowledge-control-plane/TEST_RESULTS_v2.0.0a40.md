# Test results 2.0.0a40 — breaking revision-first UI

- New revision-first UI, immutable context and profile integration tests: 17 passed.
- Knowledge-context pipeline smoke scenarios: 3 passed.
- `python -m compileall src`: passed.
- OpenAPI regeneration and canonical contract test: passed.
- Source manifest generation and verification: passed.
- ZIP integrity: passed after packaging.
- Legacy frontend tests that assert removed `/systems` and `/assistant-contexts` screens are intentionally not part of the canonical a40 regression because backward compatibility was explicitly dropped.
- Frontend production build remains externally blocked by unavailable npm packages in the configured internal registry.
