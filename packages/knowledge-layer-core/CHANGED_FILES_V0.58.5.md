# Changed files — knowledge-layer-core 0.58.5

- `knowledge_layer_core/interaction_graph.py`
  - treats loopback and localhost authorities as environment-only, non-binding evidence;
  - stops interpreting a raw Java path variable as an HTTP authority;
  - preserves environment authorities in boundary inventory and match diagnostics;
  - permits unique exact method/path matches to remain `probable` when production service URL is unresolved and only test mock URLs are observed.
- `tests/test_interaction_typed_materialization.py`
  - adds a typed materialization regression for unresolved production URL plus localhost test mock.
- version and recovery status files updated to 0.58.5.
