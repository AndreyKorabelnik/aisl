# Test results — static-analysis-runner 0.9.50

## Focused source-tree checks

This iteration changes the canonical knowledge execution path, its result contract, CLI exposure and the generic executor boundary. A full Runner regression was intentionally not executed. The focused set covers every changed production module plus the adjacent planning, architecture-audit and CLI contracts.

Result: **60 passed in 12.01s**.

Covered groups:

- canonical `knowledge-execute` and `knowledge_execution_result/v1`;
- generic Core evidence request/execution/registration;
- generic KLC materialization execution;
- input inventory and execution-plan compilation;
- execution-result contract catalog;
- knowledge architecture audit;
- knowledge catalog/profile planning;
- CLI commands and version.

Additional source-tree checks:

- `compileall`: passed;
- JSON Schema validation of the real `knowledge_execution_result/v1`: passed;
- result fingerprint validation: passed;
- source snapshot freshness rejection: passed;
- catalog fingerprint mismatch rejection: passed;
- unexpected Core output rejection: passed;
- existing evidence reuse without Core rerun: passed;
- reused registration-manifest provenance: passed;
- concrete evidence/knowledge dispatch in the canonical Runner executor: absent;
- Task/Suite/Core Profile semantic routing: absent;
- legacy fallback and dual-write: explicitly unsupported.

## Real end-to-end smoke

Executed with the supplied real modules and offline wheels:

- code-analyzer-core 0.43.27;
- static-analysis-runner 0.9.50;
- knowledge-layer-core 0.54.1;
- DuckDB 1.5.5 and tree-sitter wheels supplied with the project.

Canonical command path:

```text
knowledge_profile/v2
→ knowledge_input_inventory/v1
→ knowledge_execution_plan/v1
→ knowledge-execute
→ Core evidence runtime
→ Runner typed-artifact registration
→ KLC materialization runtime
→ knowledge_execution_result/v1
```

Result:

- status: `completed`;
- execution nodes: 2;
- analyzer executions: 1;
- evidence artifacts: 1;
- repository registration manifests: 1;
- materialization executions: 1;
- knowledge artifacts: 1;
- published capabilities: 5;
- result fingerprint: `2edd9771de951d31b967cd55425937cf83b698861ced94c4b05b47d210cc8b64`.

## Exact ZIP checks

A clean extraction of the release candidate passed:

- focused tests: **60 passed in 12.26s**;
- `compileall`: passed;
- version: `0.9.50`;
- source manifest: **456/456** files passed for the candidate tree;
- `knowledge_execution_result/v1` JSON Schema and fingerprint: passed;
- real Core → Runner → KLC canonical smoke: completed;
- evidence artifacts: 1;
- repository registration manifests: 1;
- materializations: 1;
- knowledge artifacts: 1;
- capabilities: 5;
- ZIP integrity: no errors detected.

The final archive is rebuilt only to include these verification records and its regenerated source manifest; production code is unchanged and is checked again after final packaging.

## Why no full regression

The iteration does not change repository cloning, portfolio topology, SQL parsing, workspace aggregation algorithms, existing Core analyzers, KLC materializers, Knowledge API, Reporting, Assistant or UI. Full regression is reserved for the next architecture proof that adds a second independent evidence family and materializer without Runner production changes.

## Known limits

- One real Core evidence family is currently registered.
- One real KLC handler is exercised by the canonical end-to-end path.
- Foundation caching/reuse, incremental execution and DAG parallelism are not implemented.
- Knowledge API, Reporting, Assistant and UI are not switched yet.
- Historical repository/workspace code remains for knowledge families not yet migrated, but the canonical route does not call it as fallback.
