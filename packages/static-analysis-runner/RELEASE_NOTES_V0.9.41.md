# static-analysis-runner 0.9.41 — Core/KLC responsibility map

## Added

- new `responsibility-map` command;
- deterministic `core_klc_responsibility_map/v1` contract;
- target ownership for all Core stages and produced result families;
- impact mapping to Core profiles, Runner Tasks, Suites and Analysis UI pipelines;
- current KLC import/materialization routes;
- explicit migration readiness, evidence gaps and blockers;
- Markdown export for architecture review.

## Architecture decisions recorded

- Core owns the technical Foundation and independent source-grounded evidence analyzers;
- KLC owns composition of persisted evidence into knowledge models and views;
- Runner owns orchestration and lifecycle only;
- `code_conceptual_model_build`, `system_description_enrichment`, `reference_data_fact_base` and `workspace_sql_mart_catalog_build` move to KLC;
- `java_system_interaction_enrichment` leaves Foundation and becomes an independent Core evidence analyzer;
- Task/Suite redesign and execution optimization remain deferred.

## Runtime behavior

No repository, workspace, Suite, Task, Core or Knowledge Layer execution path changed.
