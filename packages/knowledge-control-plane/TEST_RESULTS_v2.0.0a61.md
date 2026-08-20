# Test results — Analysis UI 2.0.0a61

## Completed

- `python -m compileall -q src tests` — passed.
- Mermaid/frontend/OpenAPI targeted suite — `37 passed`.
- OpenAPI regenerated; version is `2.0.0a61`.
- Source manifest generated and verified.
- Clean ZIP extraction, compileall and the same targeted suite — passed.

## Covered behavior

- generic Mermaid normalization remains enabled;
- dotted ER names and spaced flowchart labels remain handled without application-specific rules;
- `mermaid.parse(..., suppressErrors=false)` is required before render;
- `mermaid.render()` creates the SVG;
- `mermaid.run()` is absent;
- render IDs are unique;
- diagram status is visible through `data-mermaid-render-status` DOM dataset;
- parser errors are truncated and displayed through safe DOM APIs;
- stale async Mermaid results cannot overwrite newer content;
- generic API/OpenAPI contract remains current.

## Not claimed

- Full Analysis UI suite was not run for this frontend-only patch. The previous full suite had a known long-running HTTP-server completion path; only the changed and contractual frontend/API surface was run.
- `npm run build` was not executable in this container because `frontend/node_modules` is absent.

## Required runtime action

After copying the source while preserving `frontend/node_modules`:

```bash
cd packages/analysis-ui/frontend
npm run build
```

`npm ci` is not required because the dependency files did not change.
