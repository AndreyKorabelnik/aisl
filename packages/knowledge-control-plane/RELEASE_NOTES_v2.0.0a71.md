# Analysis UI 2.0.0a71

Fixes Knowledge contract discovery for the standalone `analysis-ui run` terminal path.

The CLI no longer requires manual `ANALYSIS_UI_*_CATALOG` environment variables in the standard source workspace layout (`packages/analysis-ui`, `packages/code-analyzer-core`, `packages/static-analysis-runner`, `packages/knowledge-layer-core`). Discovery now:

- resolves project roots for editable/source deployments without assuming a fixed Python package layout;
- falls back to sibling packages in the standard workspace when Core/Runner/KLC are not importable in the Analysis UI interpreter;
- selects the Knowledge catalog compatible with the discovered Core evidence and KLC materialization catalog fingerprints instead of blindly preferring a colocated/stale catalog;
- still honors explicit `ANALYSIS_UI_CORE_EVIDENCE_CATALOG`, `ANALYSIS_UI_KNOWLEDGE_CATALOG`, and `ANALYSIS_UI_MATERIALIZATION_CATALOG` overrides.

No execution path, Knowledge Profile semantics, Runner/Core/KLC behavior, or publication logic changed.
