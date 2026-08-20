# Analysis UI 2.0.0a65 — canonical knowledge execution UI

Analysis UI is fully switched to the canonical knowledge execution product route:

`Knowledge Profile → knowledge execution DAG → Core evidence → KLC materializations → Knowledge API revision → Reporting → capability-gated Assistant`.

## Product boundary

- `knowledge_execution` is the only analysis job kind.
- The UI selects knowledge outcomes and repository scope, not Task, Suite, Core Profile, analyzer or materialization IDs.
- PowerDesigner PDM is an explicit typed external input when selected knowledge requires it.
- Job progress reflects the real stages: checkout, input preparation, plan compilation, Core evidence, knowledge materialization, publication, report and Assistant readiness.
- Result pages are revision-first and read typed artifacts, capabilities, coverage and reports through Knowledge API.
- Standard chat is pinned to one immutable revision and exposes tools only from published capabilities.

## Removed without compatibility

- legacy Task/Suite/Core Profile product routing;
- `full_pipeline`, `repository_analysis` and `workspace_analysis` job kinds;
- direct combined `knowledge_layer.duckdb` handling;
- analysis-artifact registry and cache subsystem;
- job-based legacy conversation route;
- old SQL/workspace masters and profile-specific chat hints;
- automatic migration of the previous Analysis UI SQLite schema.

## Integration fixes found by the real end-to-end run

- Reporting receives the Knowledge API server root, avoiding a duplicated `/api/knowledge/v1` prefix.
- Revision chat uses the single-revision `KnowledgeApiAssistantTools`; cross-system tools remain only for attribute-addition contexts.
- Output safety no longer references the removed report-only job kind.
- Core physical-model output is wrapped in Runner's generic typed-artifact descriptor.
- KLC-owned current catalogs are selected ahead of Runner validation snapshots; the paired knowledge/materialization catalogs always come from one KLC release.

## Verification

- Full current Analysis UI regression: 53 passed.
- Architecture audit: passed.
- Python compileall: passed.
- Fresh end-to-end UI job: passed with 2 Core analyzers, 4 KLC materializations, 5 knowledge artifacts and 17 capabilities.
- Report generation and Mermaid injection: passed.
- Revision-pinned Assistant tool call `search_data_objects`: passed.
- Frontend production build was not executed because the offline npm cache lacks `vue-tsc-2.2.12.tgz`; static frontend contract tests passed.
