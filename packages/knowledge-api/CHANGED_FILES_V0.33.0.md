# Knowledge API 0.33.0 — changed files

- `knowledge_api/artifact_locator.py` — logical AISL SHA-256 locator and deterministic filesystem blob resolution.
- `knowledge_api/artifact_store.py` — publish logical content locators rather than absolute store paths.
- `knowledge_api/contract_v1/runtime.py` — resolve published content locators via current Artifact Store configuration while retaining producer `file://` validation.
- `tests/test_aisl_artifact_store.py` — logical locator/CAS tests.
- `tests/test_aisl_observed_persistence.py` — mixed observed+derived storage relocation acceptance.
- `tests/test_aisl_multifile_observed_persistence.py` — multi-file observed contract uses logical locators.
