# Test results — knowledge-api 0.16.0

## Source tree

- Full Knowledge API regression: 51 passed.
- `compileall`: passed.
- OpenAPI export equality: passed.
- Runner/API `knowledge_execution_result/v1` JSON Schema byte parity: passed.
- execution-result fingerprint/policy validation: passed.
- nested artifact path guard: passed.
- incompatible pre-0.16 SQLite catalog rejection: passed.

## Real execution publication smoke

Input: real `knowledge_execution_result/v1` from Runner 0.9.51 and KLC 0.56.0.

- CLI validate: passed.
- CLI publish: passed.
- published knowledge artifacts: 5.
- published capabilities: 17.
- effective entities: 2.
- effective fields: 5.
- effective relationships: 1.
- physical tables: 2.
- coverage: complete.
- knowledge-artifact, capability, effective-model and physical-model HTTP queries: passed.

## Test policy

Full testing was run only for Knowledge API because the public contract, persistence schema, CLI and artifact routing changed. Core, Runner, KLC, Reporting, Assistant and UI were not modified or retested.

## Clean ZIP verification

- Source manifest: passed.
- `compileall`: passed.
- Full Knowledge API regression: 51 passed, 0 failed.
- Version: 0.16.0.
- Real execution publication smoke: passed.
- ZIP integrity: passed.
