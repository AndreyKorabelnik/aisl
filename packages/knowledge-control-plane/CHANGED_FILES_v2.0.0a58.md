# Changed files — Analysis UI 2.0.0a58

- `src/analysis_ui/runtime/assistant.py` — distinguish corrected invalid tool arguments from successful Knowledge API calls in the technical trace.
- `pyproject.toml` — require `knowledge-assistant>=0.14.9,<0.15.0`.
- `VERSION`, `src/analysis_ui/__init__.py`, `README.md` — version metadata.
- `docs/api/generic-v1.openapi.json` — regenerated OpenAPI version metadata.
- `tests/test_assistant_profile_integration.py` — full HTTP test for correction of invalid model-generated tool arguments.
- `tests/test_assistant_target_handoff.py`, `tests/test_module_baseline.py` — dependency and version contract.
- `RELEASE_NOTES_v2.0.0a58.md`, `RELEASE_NOTES.md` — release documentation.
