# static-analysis-runner 0.9.44 — decomposed knowledge planning

- upgraded to `knowledge_catalog/v2`, `knowledge_profile/v2` and `knowledge_resolution_plan/v2`;
- removed user-facing `conceptual-data-model`;
- added separate code-declared model, logical-physical mapping, observed storage usage and effective model knowledge types;
- retained physical model and SQL inventory as independent knowledge;
- added explicit required/recommended knowledge dependencies;
- Resolver now expands required dependencies deterministically and reports user-requested vs implicit knowledge;
- added KLC knowledge-model dependencies to the technical preview;
- runtime analysis and UI are unchanged.
