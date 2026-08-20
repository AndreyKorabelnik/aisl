# Changed files — code-analyzer-core 0.43.17

- `code_analyzer_core/scanners/java_persistence_lineage.py`
  - derives canonical lineage status from strict evidence maturity;
  - clears stale candidate missing links only for fully confirmed paths;
  - aligns segment and inline mapping statuses with canonical maturity.
- `code_analyzer_core/navigation.py`
  - exposes `lineage_status` in compact source-to-storage lineage output.
- `tests/test_real_app_lineage_patterns.py`
  - verifies confirmed status, empty missing links and compact contract propagation.
- `pyproject.toml`, `code_analyzer_core/__init__.py`
  - version `0.43.17`.
