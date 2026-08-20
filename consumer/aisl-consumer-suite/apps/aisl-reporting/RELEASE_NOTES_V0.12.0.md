# aisl-reporting 0.12.0

## Workspace interaction business report

- Replaced the legacy correspondence/data-model-driven workspace interaction dataset with canonical boundary interactions from `knowledge-layer-core >=0.49.1,<1.0.0`.
- Added operation-centric interaction cards with HTTP method/path, source/target operations, confidence, match basis, field contracts, data groups, execution context status, evidence and limitations.
- Added bounded attribute journey cards from repository value-flow and attribute-path resolver results.
- Restored a business-context-first Russian report composition comparable to the former `workspace-system-interaction-business-report` prompt while preserving the new evidence model.
- Added interaction coverage, unmatched outbound diagnostics, strict/extended island facts and explicit confirmed/probable discipline.
- Removed the exact KLC 0.29.0 dependency pin.
- Replaced N×resolver traversal with deterministic pre-ranking and a bounded shortlist; preparation on the four-repository validation workspace now completes in 11.61 seconds.
- Removed machine-local absolute paths from deterministic report datasets and nested evidence packets.

No compatibility dataset or dual-write is retained for the old generic correspondence sections.
## Validation

- Compared the new prompt and report contract with `workspace-system-interaction-business-report` from `llm-prompts 0.31.0`.
- Prepared the dataset on a real two-repository UCP workspace: 1 probable interaction, 7 field contracts, 7 candidate transport edges and 5 bounded attribute journeys.
- Full module regression: 44 passed, 13 fixture-dependent skipped, 0 failed.

