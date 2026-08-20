# Changed Files — aisl-reporting 0.2.0

- `pyproject.toml` — public dependency on `aisl-client>=0.1.0,<0.2.0`.
- `aisl_reporting/knowledge_api.py` — removed duplicate Knowledge API HTTP client and active-revision resolver; reporting-specific source/requirement/selection adapter now consumes public `AislClient`.
- `aisl_reporting/pipeline.py` — creates the public SDK client and resolves a pinned revision through the reporting adapter.
- `aisl_reporting/__init__.py` — removed the old `KnowledgeApiClient` export; no compatibility alias retained.
- `VERSION`, `aisl_reporting/version.py` — version 0.2.0.
- `README.md`, `RELEASE_NOTES_V0.2.0.md`, `TEST_RESULTS_V0.2.0.md` — public SDK boundary and validation.
