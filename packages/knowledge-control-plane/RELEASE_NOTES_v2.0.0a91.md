# analysis-ui 2.0.0a91

Small architecture-boundary follow-up after the Profile/Scenario split.

The Scenario contract now contains only fields that participate in user workflow orchestration. The unused `analysis_purposes` and `requires_llm` selectors were removed rather than retained as speculative future semantics.

Pinned runtime catalogs were regenerated from the current canonical owners: code-analyzer-core 0.44.21, knowledge-layer-core 0.59.49 and static-analysis-runner 0.10.17.
