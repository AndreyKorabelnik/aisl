# Core 0.44.15 changed files

- `code_analyzer_core/sql_profile.py` — guard lazy SQLGlot `selected_sources` resolution so duplicate aliases do not abort repository analysis.
- `tests/test_sql_scoped_relations.py` — regression test for duplicate relation aliases.
- version metadata and release/test notes updated.
