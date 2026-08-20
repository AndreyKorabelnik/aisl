# Test results — knowledge-layer-core 0.35.0

- Focused object-lineage contract tests: 4 passed.
- Affected system-interaction regression: 15 passed.
- Python compileall: passed.
- Real four-system replay: complete.
- Graph: 4 systems / 3 system edges / 9 operation edges.
- Request field contracts: 231.
- Request field lineage: 58.
- Response field lineage: 36.
- Total field lineage: 94; all prior 94 IDs preserved.
- Whole-object lineage: 1 (`UserInfo`, `identity_object`, 6 occurrences / 5 edges).
- Manual response baseline: 21 / 21 when field and object lineage are combined.
- Full/deep regression intentionally not executed.
