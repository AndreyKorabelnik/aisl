# Analysis UI 2.0.0a62 — knowledge execution backend

First delivery of the Analysis UI migration to the generic knowledge execution architecture.

- Public jobs accept only `knowledge_execution`.
- User-facing registry exposes Knowledge Profiles and knowledge outcomes, not Task/Suite/Core Profile.
- Backend compiles input inventory and `knowledge_execution_plan/v1`, executes `knowledge-execute`, publishes a Knowledge API revision, builds a report from a pinned revision and creates a capability-gated Assistant context.
- Added `/api/v1/knowledge-profiles`.
- Removed product routes for legacy profiles, analysis-artifacts and job-based conversations.
- Typed execution contracts and knowledge artifacts are registered separately.
- No compatibility adapter, fallback or dual-write is provided.
