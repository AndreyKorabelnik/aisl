# knowledge-api 0.26.2

Legacy Cleanup Block 2 removes `dual_write` from the current Knowledge Execution publication contract.

## What changed

- Publication no longer requires a permanent marker saying dual-write is unsupported.
- Removed the property from the current `knowledge_execution_result/v1` JSON schema.
- Capability-publication validation remains enforced.
- OpenAPI is regenerated for 0.26.2.
