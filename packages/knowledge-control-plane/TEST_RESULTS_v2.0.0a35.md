# Test results 2.0.0a35

- Focused profile/context regression: 8 passed.
- Full Analysis UI backend suite: 121 passed.
- `compileall src/analysis_ui`: passed.
- Generated OpenAPI updated to 2.0.0a35 and verified by the full suite.
- Real standard endpoint before/after probe used newly published UCP, datamart and PDM revisions.
- Before: 6740 prompt characters; complete profile absent; shortened local instruction present.
- After: 14291 prompt characters; complete `attribute-addition-plan/v1` present; profile ID/version/fingerprint/load status returned in diagnostics.
- Frontend source was not changed; npm/Vite production build was not run.
- Full platform ingestion/parser suite was not repeated for this isolated UI integration change.
