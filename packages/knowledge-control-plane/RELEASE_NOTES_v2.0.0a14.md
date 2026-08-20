# analysis-ui 2.0.0a14 — orchestration-only runtime

Iteration 17 completes the ownership split with `knowledge-api`.

## Changed

- removed `analysis_ui.domain.systems` and its semantic query adapter;
- removed all local `/api/v1/systems/**`, data-model and report routes from runtime and design-time OpenAPI;
- removed `SystemCatalogService` from `RuntimeContext` and `JobManager`;
- removed `knowledge-layer-core` from `analysis-ui` dependencies;
- removed local system/revision store methods and added startup cleanup for legacy SQLite tables;
- retained HTTP publication, publication retry and transparent `/api/knowledge/v1/**` proxy;
- made OpenAPI explicitly orchestration-only;
- fixed the frontend README baseline classification introduced in iteration 16.

No Vue template or style section changed.
