# Test results — static-analysis-runner 0.9.41

## Scope

This iteration adds a read-only architecture artifact. Repository/workspace/Suite/Task execution and Knowledge Layer materialization were not changed, so full regression was intentionally not run.

## Targeted tests

Groups:

- mechanism catalog and responsibility map;
- CLI version and command parsing;
- built-in Suite catalog.

Result:

```text
26 passed
```

Covered:

- Foundation, independent evidence analyzer and packaging ownership;
- explicit KLC migration policy;
- affected profile/Task/Suite routing;
- deterministic JSON and Markdown output;
- CLI execution;
- mechanism catalog fingerprint rejection;
- existing official Core catalog composition contracts;
- version and built-in Suite catalog smoke.

## Real integration

The responsibility map was generated from the real `analysis_mechanism_catalog/v4` composed from:

- code-analyzer-core 0.43.21;
- static-analysis-runner 0.9.40 mechanism catalog;
- knowledge-layer-core 0.53.7;
- analysis-ui 2.0.0a61.

Observed result:

- 48 Core stages;
- 67 produced result families;
- 10 current Foundation stages;
- 9 target Foundation/source-index stages;
- 30 target independent evidence analyzer stages;
- 4 knowledge materializations to move to KLC;
- 5 technical packaging stages;
- `java_system_interaction_enrichment` must leave Foundation.

Migration order:

1. `code_conceptual_model_build`;
2. `system_description_enrichment`;
3. `reference_data_fact_base`;
4. `workspace_sql_mart_catalog_build`.

## Additional checks

- `compileall`: passed;
- real JSON schema and count assertions: passed;
- real migration order assertion: passed;
- execution effect: `none`.
