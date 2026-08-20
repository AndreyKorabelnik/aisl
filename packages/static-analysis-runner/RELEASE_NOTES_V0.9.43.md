# static-analysis-runner 0.9.43 — User knowledge planning contracts

## Added

- user-facing `knowledge_catalog/v1` compiled from official Core/KLC/Runner contracts;
- user-owned `knowledge_profile/v1` for repository or workspace scope;
- deterministic read-only `knowledge_resolution_plan/v1`;
- explicit preview of what enters the Knowledge Layer and which Core evidence sources support it;
- separate current-runtime and target-contract readiness statuses;
- advanced-only technical lineage to Core stages and Foundation requirements;
- CLI commands `knowledge-catalog` and `knowledge-profile-resolve`.

## Product boundary

Users select business knowledge, scope and presentation/coverage options. They do not create or select Core stages, Core profiles, Tasks, Suites, KLC materializations or technical artifact schemas.

## Runtime behavior

No repository, workspace, Suite, Task, Core, KLC or Analysis UI runtime path changed. The resolution plan is diagnostic only and does not execute analysis.
