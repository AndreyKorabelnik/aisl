# Changed files in 0.40.9

- `code_analyzer_core/scanners/java_field_flow_builder.py`
  - preserve nested invocation receivers and emit `invocation_receiver` edges
- `tests/test_java_tree_sitter_field_flow.py`
  - chained collection getter and exact boundary reachability regressions
- `code_analyzer_core/__init__.py`
- `pyproject.toml`
- `RELEASE_NOTES_V0.40.9.md`
