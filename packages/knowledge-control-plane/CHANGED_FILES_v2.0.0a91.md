# analysis-ui 2.0.0a91 — Scenario contract cleanup

- Removed unused `analysis_purposes` from `ScenarioDefinition`.
- Removed unused `requires_llm` from `ScenarioDefinition`.
- Regenerated pinned Core/KLC/Runner catalogs from canonical owner builders using Core 0.44.21, KLC 0.59.49 and Runner 0.10.17.
- Regenerated OpenAPI after the Scenario contract cleanup.
- Extended architecture audit to prohibit dead Scenario selectors.

No Producer, Knowledge API, Reporting or Assistant runtime semantics are implemented in Analysis UI.
