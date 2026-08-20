# Changed files in 0.29.1

- `knowledge_layer_core/query.py`
  - adds full missing-fact detail lookup.
- `knowledge_layer_core/workspace_evidence.py`
  - adds the workspace-scoped detail evidence command.
- `knowledge_layer_core/evidence.py`
  - publishes the command through the canonical knowledge-layer evidence catalog.
- `tests/test_workspace_data_model.py`, `tests/test_evidence.py`
  - verify compact list behavior, payload detail, evidence-tool execution and `not_found` behavior.
- `knowledge_layer_core/version.py`, `pyproject.toml`, `tests/test_offline_validation.py`
  - version `0.29.1`.
- `README.md`, `TEST_RESULTS.md`, release/validation metadata.
