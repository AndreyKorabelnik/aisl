# knowledge-layer-core 0.29.0

## Iteration 26

- introduces the deterministic `analysis_coverage/v1` projection;
- aggregates existing observed facts, missing facts, unresolved relationship candidates and storage-encoding limitations without creating a second gap model;
- exposes coverage through `KnowledgeLayerQuery` and `ReportingQueryService`;
- states explicitly that absence of evidence does not prove absence in source systems;
- reports diagnostic occurrences rather than accuracy percentages or subjective confidence scores.
