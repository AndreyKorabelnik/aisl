# analysis-ui 2.0.0a90 — Knowledge Profile / Scenario boundary

- Replaced mixed `ProfileInfo` runtime model with separate `KnowledgeProfileDefinition` and `ScenarioDefinition`.
- Knowledge Profiles now own only exact reusable knowledge composition and execution scope kind.
- Scenarios own source/context UX, report selection, Assistant policy, presentation choices and scenario parameters.
- Jobs execute a `scenario_id` and persist both `scenario_id` and resolved `knowledge_profile_id`.
- Removed per-job `knowledge_ids` and `report_profile` overrides; the execution snapshot uses the exact referenced Knowledge Profile.
- Replaced `/masters/:profileId` with `/scenarios/:scenarioId`; no compatibility route is retained.
- Simplified Control Plane stages to `runner_plan` and `runner_execution`; Core/KLC stages remain Runner internals.
- Regenerated pinned Core/KLC/Runner catalogs from Core 0.44.20, KLC 0.59.49 and Runner 0.10.17 using owner builders.
- Regenerated OpenAPI and architecture audit.
