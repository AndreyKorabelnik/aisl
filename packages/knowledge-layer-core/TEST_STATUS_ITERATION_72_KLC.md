# Test status — iteration 72 KLC

- `compileall`: passed.
- `tests/test_sql_analysis_knowledge_layer.py`: 6 passed.
- Synthetic ambiguous usage includes three scoped relations, one JOIN and one projection.
- Missing usage returns deterministic `not_found` result.
- No unrelated full regression was run.
