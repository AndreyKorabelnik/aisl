# Changed files — analysis-ui 2.0.0a27

- `src/analysis_ui/runtime/analysis_artifacts.py` — safe registration, manifest parsing, hashing and registry lifecycle for existing DuckDB artifacts.
- `src/analysis_ui/runtime/knowledge_publication.py` — immutable Knowledge API publication for registered DuckDB files.
- `src/analysis_ui/runtime/store.py`, `context.py`, `routes.py` — durable metadata, runtime wiring and CRUD endpoints.
- `src/analysis_ui/api/generic_v1/models.py`, `contract.py` — typed artifact registry API and OpenAPI resource declaration.
- `tests/test_analysis_artifacts.py` — complete/bare manifest, path safety, publication and registry lifecycle regression.
- Runtime/store/OpenAPI tests, README, version and release metadata synchronized.
