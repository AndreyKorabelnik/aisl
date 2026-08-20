# analysis-ui 2.0.0a94

## Knowledge Profiles + Production Structure Explorer

- persistent unified platform/user Knowledge Profile Registry in the Analysis Control Plane;
- create, copy, edit and delete user Knowledge Profiles; platform profiles remain read-only/copyable;
- Runner-owned Knowledge Product Catalog projection with runtime/selectability/scope/dependency metadata;
- Runner-backed profile validation/resolution; UI does not own dependency semantics;
- Scenario Wizard can select any saved profile compatible with the scenario context scope while preserving Scenario/Profile separation;
- scenario-specific report generation is disabled when a different profile is selected;
- planned Production Structure exposes selected products, implicit Runner dependencies, Core/external evidence, KLC materializations and knowledge-model dependencies;
- actual Production Structure is read from immutable profile/plan/result snapshots of the run;
- planned-vs-actual execution view;
- generic Core/KLC/Prepared artifact technical inspector with coverage, diagnostics, metadata and fingerprints;
- generic text/JSON artifact content preview from the existing artifact read endpoint;
- Prepared Revision view links back to the immutable production structure through orchestration_job_id when available;
- no Prepared Knowledge editing, second resolver, second planner or parked-scope resumption.

## Validation

- full Analysis UI Python suite before version cut: 84/84 PASS;
- frontend boundary verification: PASS;
- architecture audit: PASS;
- frontend production build remains separately reported because the offline npm cache may not contain all dependencies.
