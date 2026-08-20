# analysis-ui 2.0.0a88

Architecture Boundary Simplification — Analysis Control Plane -> Runner.

- Analysis UI no longer invokes `code-analyzer-core` directly for PDM preparation.
- Analysis UI no longer constructs `physical-model/v1` typed-artifact envelopes.
- Analysis UI no longer converts Knowledge API artifacts into Runner existing-knowledge descriptors.
- Published Knowledge revisions are persisted as immutable snapshots and passed raw to Runner.
- Job input preparation now delegates to Runner `knowledge-input-prepare`.
- Removed `code_analyzer_core` from Analysis UI command configuration/public configuration contract.
- Regenerated pinned runtime catalogs from Core 0.44.20 / Runner 0.10.16 / KLC 0.59.47.
- Updated Analysis UI dependency to `knowledge-assistant>=0.25.0,<0.26.0`.
