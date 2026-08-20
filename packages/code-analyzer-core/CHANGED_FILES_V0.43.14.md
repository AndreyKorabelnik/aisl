# Changed files — code-analyzer-core 0.43.14

- `code_analyzer_core/scanners/java_persistence_lineage.py`
  - adds exact source-declared inherited-method dispatch edges;
  - adds exact source-declared virtual override edges for template methods;
  - keeps synthetic edges isolated in the persistence interprocedural index.
- `tests/test_real_app_lineage_patterns.py`
  - adds a generic inheritance/template-method regression fixture.
- `pyproject.toml`, `code_analyzer_core/__init__.py`
  - version `0.43.14`.
