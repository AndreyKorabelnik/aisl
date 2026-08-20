# AISL Reporting extraction

`aisl-reporting 0.1.0` is extracted from the former framework package `knowledge-reporting 0.18.1`.

Architectural changes:
- distribution/package/CLI renamed to `aisl-reporting` / `aisl_reporting` / `aisl-reporting`;
- runtime source is a published Knowledge API revision (`api_url + system_id + revision_id`);
- direct local `git-change-impact-report/v1` input was intentionally removed;
- dependency on `evidence-common` was removed; OpenAI-compatible rendering is local to this consumer;
- no Core, Runner, KLC, KCP or Knowledge API Python package dependency is required.

This is a presentation consumer. Its report outputs are not AISL KnowledgeRevision members.
