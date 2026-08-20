# Runner 0.10.11 changed files

- evidence/knowledge execution, planning, materialization and data-model discovery: removed the `dual_write` semantic-policy tombstone.
- `knowledge_execution.py`: removed the tombstone rule and now validates the exact current policy shape without `dual_write`.
- current execution plan/result schemas: removed `dual_write`.
- targeted tests now verify absence.
- version metadata updated to 0.10.11.
