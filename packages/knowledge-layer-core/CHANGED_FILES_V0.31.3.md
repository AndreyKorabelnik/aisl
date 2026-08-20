# Changed files in 0.31.3

- `knowledge_layer_core/interaction_lineage.py`
  - compose confirmed derivations located directly in an exactly resolved mapper operation;
  - retain existing helper-derivation composition;
  - publish direct-mapper provenance without a synthetic helper call.
- `tests/test_system_interaction_graph.py`
  - exact direct-mapper composition regression;
  - ambiguous/wrong-type derivations remain excluded.
- `knowledge_layer_core/version.py`
- `pyproject.toml`
- `README.md`
- `RELEASE_NOTES_V0.31.3.md`
- `TEST_RESULTS.md`
