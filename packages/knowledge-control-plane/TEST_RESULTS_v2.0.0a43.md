# Test results 2.0.0a43 — system interaction master

## Confirmed

- Focused profile, pipeline and revision UI tests: 17 passed in two isolated runs (11 + 6).
- Real Analysis UI end-to-end smoke with two repositories: succeeded.
  - fixed runner suite: `system-interaction-lineage`;
  - workspace manifest: `static_workspace_analysis_run_manifest/v2`;
  - Knowledge Layer capabilities include `suite.interaction-lineage` and `workspace.repository-interaction-coverage`;
  - report prepared through `workspace-interaction/v1` with a deterministic response file;
  - immutable revision `revision-1` published;
  - standard revision chat context created;
  - 447 artifacts registered;
  - all five pipeline stages completed or were intentionally skipped.
- The minimal fixture produced zero outbound interactions. This remained a successful, explicit coverage result; no fallback edge was invented.
- Python compileall: passed.
- OpenAPI generation: passed.
- Frontend orchestration/Knowledge API boundary check: passed.
- TypeScript and Vue script syntax check: passed.
- Source manifest and ZIP integrity: checked after packaging.

## Known limitations

- The deterministic smoke response intentionally does not emulate a complete LLM-rendered business report; report validation records heading/citation warnings while the pipeline and report artifact remain valid.
- Production frontend build was not run because the available npm dependency set is incomplete.
- No Core or Knowledge Layer matching algorithm was changed in this release.
