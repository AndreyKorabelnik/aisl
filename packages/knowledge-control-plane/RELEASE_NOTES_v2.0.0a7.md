# analysis-ui 2.0.0a7

Iteration 7 validates the complete runtime against the real framework CLIs and embeds the public `knowledge-api 0.2.2` application into the same server process.

## Corrected from production smoke

- repository Knowledge Layer materialization now passes the real runner-required `--task-id` and `--profile-id` arguments;
- analysis profiles are mapped to canonical task IDs, including `repository-data-model-static -> data-model`;
- retry from `knowledge_materialization` prioritizes the canonical repository/suite manifest instead of a nested technical manifest;
- `full_pipeline` propagates reporting options including `response_file`, strict validation, timeouts and output naming;
- data-model pipelines reject a suite-only or capability-mismatched Knowledge Layer rather than publishing an empty successful result;
- executable version probes are cached per resolved binary and file revision, preventing repeated subprocess startup during capability, doctor and diagnostics calls.

## Embedded data-model API

`analysis-ui serve` now mounts the public routes produced by the supported `knowledge_api.create_app()` factory:

```text
GET /health
GET /api/v1/systems
GET /api/v1/systems/{system_id}/field-catalog
GET /api/v1/systems/{system_id}/report
GET /api/v1/systems/{system_id}/tables/{table_id}
```

The actual `knowledge-api 0.2.2` contract has no separate `GET .../tables` list route. `field-catalog` is the canonical table/field catalog. The frontend `listTables()` method is retained only as an alias to `field-catalog`.

## Real production smoke

A fresh job was executed through the generic HTTP API with the real component versions:

```text
static-analysis-runner 0.9.7
knowledge-reporting    0.9.2
code-analyzer-core     0.38.0
knowledge-layer-core   0.24.0
knowledge-api          0.2.2
```

The job completed `static_analysis`, `knowledge_materialization`, and `report_build`, produced 184 registered artifacts and 300 durable SSE events, and passed strict report validation. Generic logs, commands, artifact download, diagnostics bundle, comparison, and all five data-model routes were exercised in the same server process.

## Preserved

- all 20 Vue template/style sections remain identical to UI2 1.4.7;
- generic API v1 remains the orchestration contract;
- diagnostics bundles remain metadata-only and sanitized;
- no source package was built into a wheel during validation.
