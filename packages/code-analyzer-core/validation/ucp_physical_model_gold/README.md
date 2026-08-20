# UCP physical-model gold validation

This regression asset validates the four failure modes found by comparing the framework with a manual analysis of ten real UCP repositories:

1. rollback/manual/test/demo SQL must not mutate the effective production schema;
2. directory/module names must not be invented as database schemas;
3. direct PostgreSQL `CREATE TABLE ... PARTITION OF ...` children must be physical table objects with inherited-column provenance;
4. the integrated WKL result must retain the expected real UCP objects.

The ordinary test suite uses a compact synthetic fixture (`tests/test_ucp_physical_model_regression.py`). The script in this directory validates a real generated WKL DuckDB workspace without embedding proprietary source repositories in the code archive.

Example:

```bash
python validation/ucp_physical_model_gold/validate_workspace.py \
  /path/to/workspace.duckdb \
  --output /tmp/ucp-gold-result.json
```
