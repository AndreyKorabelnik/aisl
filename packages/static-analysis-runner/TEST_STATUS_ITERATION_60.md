# Test status — iteration 60

## Result

Status: **passed**

Environment:

- Python `3.13.5`;
- pytest `9.0.2`;
- DuckDB `1.5.5` wheel;
- knowledge-layer-core `0.49.1` source package for existing materialization tests;
- code-analyzer-core `0.42.2` for real SQL E2E.

## Fast and contract tests

- `compileall static_analysis_runner tests`: passed;
- full runner test suite: **65 passed in 20.01s**;
- SQL-focused/profile/repository subset: **27 passed**.

Covered SQL cases include:

- strong SQL profile routing and Java fallback;
- unsupported explicit analyzer rejection;
- minimum core version `0.42.2`;
- valid partial `sql-analysis/v1` artifact;
- tampered JSONL shard;
- malformed fact entry;
- unsafe shard path;
- explicit rejection of premature SQL Knowledge Layer materialization.

## Real repository E2E

Input: `datamart_profile_fl`.

Flow:

```text
static-analysis-runner 0.9.25
→ code-analyzer-core 0.42.2 analyze-sql
→ sql-analysis/v1 validation
```

Result:

- runner status: `completed`;
- validation status: `valid`;
- analysis status: `partial`;
- warning codes: `analysis_partial`;
- error codes: none;
- canonical facts: `27,600`;
- content fingerprint:
  `5fffb63d9f7e5ebbdd2261b13aec0e33ee7eae9ef0cc8b3b324edfc3674a6c69`;
- core elapsed time: `14.535 s`;
- core maximum RSS: `579,668 KB`.

## Known test-environment issue resolved

The combined suite initially showed long startup delays in short Python-based fake tools
because they inherited unrelated global site initialization. Test doubles now use the
active interpreter with `-S`. Production subprocess orchestration was not changed.
