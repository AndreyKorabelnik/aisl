# Test status — code-analyzer-core 0.44.8

- Targeted tests (`test_sql_script_calls.py`, `test_sql_generic_evidence.py`): **3 passed**.
- `compileall` for `code_analyzer_core`: **OK**.
- Real datamart artifact: **412** `sql_script_call` facts.
- Known baseline condition: SQL analysis remains `partial` because of pre-existing explicit SQL diagnostics; this release does not hide or reinterpret them.
