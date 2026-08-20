# code-analyzer-core 0.44.10

- `code_analyzer_core/sql_profile.py`
  - parser view now omits a standalone dynamic SQL fragment placeholder only when it follows a statically complete `FROM <relation> [alias]` clause;
  - semantic placeholder evidence is still preserved unchanged;
  - prevents template fragments such as optional JOIN filters from truncating the remaining CTE graph.
- `tests/test_sql_semantic_placeholders.py`
  - regression for multi-CTE query with standalone relation-suffix placeholder.
- package version: 0.44.10.
