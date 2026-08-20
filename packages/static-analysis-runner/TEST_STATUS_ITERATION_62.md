# Test status — iteration 62

## Result

Status: **passed**

Environment:

- Python `3.13.5`;
- DuckDB `1.5.5` wheel;
- code-analyzer-core `0.42.2`;
- knowledge-layer-core `0.50.0`;
- sqlglot `30.13.0`.

## Automated tests

- `compileall static_analysis_runner tests`: passed;
- full runner suite: **69 passed**;
- SQL-focused suite: **14 passed**;
- real KLC SQL materialization contract: passed;
- manifest-driven additive SQL stream: passed;
- duplicate fact type/path validation: passed.

## Real repository E2E

Input: `datamart_profile_fl`.

```text
static-analysis-runner 0.9.26 repository --materialize-knowledge
→ code-analyzer-core 0.42.2 analyze-sql
→ sql-analysis/v1
→ knowledge-layer-core 0.50.0
→ knowledge-layer.duckdb
```

Result:

- runner status: `completed`;
- SQL validation: `valid`;
- source analysis status: `partial`;
- warning: `analysis_partial`;
- facts: `27,600`;
- KLC status: `complete`;
- KLC capabilities: `common.sql-analysis`, `common.sql-relation-fields`;
- clean precheck ZIP: manifest, compileall, ZIP integrity and **69 tests passed**;
- source fingerprint preserved:
  `5fffb63d9f7e5ebbdd2261b13aec0e33ee7eae9ef0cc8b3b324edfc3674a6c69`;
- total elapsed time in the programmatic E2E: `21.949 s`.

## Relation-field smoke query

- relation kind: `physical_template`;
- logical relations returned: `195`;
- sample `${$app.pa.schema.name}.$pa_table` fields:
  `flags_txt`, `part_1_month`, `sid`;
- field roles preserved: `projection`, `join`;
- coverage remains visible as `partial`.
