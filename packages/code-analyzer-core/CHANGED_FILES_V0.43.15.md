# Changed files — code-analyzer-core 0.43.15

- `code_analyzer_core/scanners/java_persistence_lineage.py`
  - preserves concrete dispatch context through template-method reverse traversal;
  - filters inherited calls from sibling handler types;
  - resolves stream-to-map value projections, map lookups and collection setter provenance.
- `tests/test_real_app_lineage_patterns.py`
  - adds a generic two-handler regression proving that Kafka provenance is not replaced by an unrelated REST ingress.
- `pyproject.toml`, `code_analyzer_core/__init__.py`
  - version `0.43.15`.
