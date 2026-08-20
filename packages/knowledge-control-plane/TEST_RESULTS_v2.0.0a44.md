# Test results 2.0.0a44 — system description master

## Confirmed

- Focused backend and revision-first UI tests: 13 passed.
- Real Analysis UI end-to-end smoke with one Java repository: succeeded.
  - fixed runner suite: `default-system-analysis`;
  - workspace manifest: `static_workspace_analysis_run_manifest/v2`;
  - required Knowledge Layer capabilities: `suite.system-description` and `suite.data-model`;
  - fixed report: `system-description/v1`;
  - immutable revision `revision-1` published;
  - standard revision chat context created;
  - 428 artifacts registered;
  - all five pipeline stages completed or were intentionally skipped;
  - initial chat history contained zero persisted welcome messages.
- Repository target is rejected as `workspace_required`.
- Conflicting `analysis_profile_id` cannot replace the fixed suite.
- Python compileall: passed.
- OpenAPI generation: passed.
- Frontend orchestration/Knowledge API boundary check: passed.
- TypeScript and Vue script syntax check: passed.
- Source manifest and ZIP integrity: checked after packaging.

## Known limitations

- The E2E report used a deterministic response file to verify orchestration and publication; it does not claim full LLM rendering quality.
- Production frontend build was not run because the available npm dependency set is incomplete.
- No Core, Knowledge Layer or reporting algorithm was changed in this release.
