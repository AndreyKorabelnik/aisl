# Test Results — aisl-reporting 0.2.0

- `tests/test_knowledge_api_reporting.py`: 6/6 PASS
- full `aisl-reporting` suite: 93/93 PASS
- compile/import: PASS
- deterministic before/after dataset comparison against the same HTTP mock contract: byte-identical, SHA-256 `49cd8c80bdf76c5ee264f860205553672aff5a2646bd0d5244f601c77d13a71e`

No full framework regression was run because framework runtime code is unchanged by this consumer migration.
