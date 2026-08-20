# Changed files — code-analyzer-core 0.43.16

- `code_analyzer_core/scanners/java_persistence_lineage.py`
  - splits multi-table JOOQ projections by exact `TABLE.FIELD` ownership;
  - adds exact `record.getValue(TABLE.FIELD) → builder.field(...)` mappings;
  - preserves return propagation for unqualified `this`/`super` calls.
- `tests/test_real_app_lineage_patterns.py`
  - adds a generic multi-table JOOQ builder-to-REST regression.
- `pyproject.toml`, `code_analyzer_core/__init__.py`
  - version `0.43.16`.
