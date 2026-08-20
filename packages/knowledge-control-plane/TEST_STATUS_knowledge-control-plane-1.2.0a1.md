# Test status — Knowledge Control Plane 1.2.0a1

## PASS

- Full Python/static contract suite after version finalization: **94/94 PASS**.
- Auto-refresh + Production UI targeted acceptance: **10/10 PASS** (8 refresh semantics + 2 UI/control-boundary tests).
- Version/package baseline included in final targeted validation: PASS.
- Knowledge-execution architecture audit: PASS; the audit explicitly requires ProductionService, FreshnessService, Productions UI and Production refresh API routes.
- Generated OpenAPI: PASS; title `Knowledge Control Plane Knowledge Execution API`, 44 paths.
- Direct frontend orchestration / Knowledge API boundary check: PASS.
- Direct frontend dependency portability check: PASS; public HTTPS registry references only, no private credentials/host in `.npmrc`.
- Python compile/import: PASS; `knowledge_control_plane.__version__ == 1.2.0a1`.
- Active runtime rename check: no `analysis-ui`, `analysis_ui` or `ANALYSIS_UI` token in `src/` or `frontend/src/`.

## NOT VERIFIED / ENVIRONMENT LIMITATIONS

- Real Bitbucket network/credentials auto-refresh smoke: **NOT VERIFIED** in this environment.
- Frontend production build: **NOT RUN** because `frontend/node_modules/.bin/vue-tsc` and `frontend/node_modules/.bin/vite` are unavailable offline. Static frontend contract/dependency tests above are PASS, but they are not a substitute for the production build.

## Packaging

- Source-tree manifest: PASS after final source/release metadata edits.
- Module source ZIP integrity: PASS.
- Wheel build without build isolation and without dependency resolution: PASS.
- Wheel ZIP integrity: PASS.
- Wheel installed to an isolated target and imported as `knowledge_control_plane 1.2.0a1`: PASS.
- `knowledge-control-plane refresh-check --help` from the installed wheel with runtime dependencies provided by the canonical test environment: PASS.
- A deliberately `--no-deps` venv could import the package but could not start the CLI because third-party `uvicorn` was absent; this is expected dependency absence and is not counted as CLI PASS.

Top-level all-modules ZIP and recovery checksum verification are recorded in the delivery/recovery metadata.
