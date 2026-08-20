# Changed files — Analysis UI 2.0.0a59

- `src/analysis_ui/runtime/settings.py` — separate `KNOWLEDGE_API_PUBLICATION_TIMEOUT_SECONDS` setting with a 600-second default.
- `src/analysis_ui/runtime/context.py` — pass the dedicated publication timeout to the canonical Knowledge API client.
- `src/analysis_ui/runtime/knowledge_publication.py` — use the long timeout only for revision publication and distinguish timeout from service unavailability.
- `tests/test_knowledge_api_publication.py` — delayed-publication success and precise timeout regressions.
- `tests/test_knowledge_api_timeouts.py` — environment/default contract for independent timeouts.
- `VERSION`, `pyproject.toml`, `src/analysis_ui/__init__.py`, `README.md` — version and operating instructions.
- `docs/api/generic-v1.openapi.json` — regenerated version metadata.
- `RELEASE_NOTES_v2.0.0a59.md`, `RELEASE_NOTES.md`, `TEST_RESULTS_v2.0.0a59.md` — release documentation.
