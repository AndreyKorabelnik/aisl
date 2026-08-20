# Test status — iteration 90 KLC

## Focused tests

`tests/test_sql_analysis_knowledge_layer.py`: **10 passed, 0 failed**.

Covered:

- exact 18-stream artifact contract;
- typed import;
- counts and schema validation;
- literal/template workflow binding query;
- provenance and capability exposure;
- existing target-column lineage and SQL query contracts in the same affected module.

## Real repository smoke

- source: code-analyzer-core 0.43.7 canonical artifact for `datamart_profile_fl`;
- KLC build: complete;
- workflow bindings imported: 2,853;
- `epk_client`: 6;
- `epk_client_v2`: 9;
- capability and read-only query: successful.

## Deliberately not run

The full KLC suite was not run. No common workspace schema, data-model materialization, UCP relationships, topology, attribute paths or portfolio features were modified.
