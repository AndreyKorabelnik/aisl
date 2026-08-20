# knowledge-layer-core 0.29.1

Iteration 28.2C exposes complete missing-fact diagnostics without expanding compact catalogs.

- `workspace_missing_fact.payload_json` continues to preserve each imported gap record verbatim;
- adds `KnowledgeLayerQuery.missing_fact_detail(gap_id)`;
- adds public evidence command `workspace_data_model_missing_fact_detail`;
- detail results include full `payload_json` plus source `evidence_ref` rows;
- list and grouped summary queries remain compact and do not copy raw payloads;
- unknown gap identifiers return an explicit `not_found` result without inference.

The schema is unchanged; this is a query/consumer-contract extension over the existing JSON payload column.
