# Changed files in 0.31.2

- `knowledge_layer_core/interaction_lineage.py`
  - retain terminal contract fields;
  - exclude coarse whole-object contribution edges from field-level lineage;
  - suppress unverified collection-container wire mappings;
  - preserve exact scalar and collection transformation paths.
- `tests/test_system_interaction_graph.py`
  - terminal contract field regression;
  - coarse whole-object path rejection regression;
  - unverified collection-container rejection with scalar safety regression.
- `knowledge_layer_core/version.py`
- `pyproject.toml`
- `README.md`
- `RELEASE_NOTES_V0.31.2.md`
