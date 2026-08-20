# Change report — AISL consumer ergonomics read projection

Date: 2026-08-15
Status: **CONSUMER_ERGONOMICS_READ_PROJECTION_BLOCK_COMPLETE**

## Evidence for the change

The existing external attribute-addition tool `get_data_model_attribute_extension_context` was bound directly to the full canonical `data-model-attribute-extension-context` response. That payload is valuable for exact verification, but it places KLC-owned actionability (`basis.usefulness`) below identity/evidence detail and can carry large SQL/provenance collections. This matches the prior real consumer feedback preserved in the handover: answers were too detailed while relation/JOIN context was not visible early enough.

The recovery contains real multicase AISL acceptance for the composed revision, but it does not contain a live Knowledge API catalog or a captured post-change external-agent trace. Therefore this block changes only the proven read ergonomic issue and does not claim a new real LLM quality score.

## Changed modules

### knowledge-api 0.30.12

- Added `GET /api/knowledge/v1/systems/{system_id}/data-model/attribute-extension-guidance`.
- The endpoint reuses the existing canonical attribute-extension read, then only selects, reorders and bounds already-published fields.
- KLC-owned `usefulness` is promoted verbatim; technical `confidence`, `ambiguity`, residual checks, diagnostics and gaps are preserved.
- Exact-vs-analog SQL JOIN relevance, predicates, storage-reference observations, key/reference expressions and compact SQL anchors are surfaced early.
- Occurrence-id noise and empty sections are omitted from the consumer view; one stable `join_semantic_id` plus readable source/target identity remains.
- Truncation is explicit. The full canonical `/data-model/attribute-extension-context` route remains unchanged for targeted verification.
- No semantic derivation was added to Knowledge API.

### knowledge-integration 0.1.11

- Keeps the existing tool name `get_data_model_attribute_extension_context`; tool count does not increase.
- That tool now binds to the compact guidance route.
- `attribute-addition-plan/v1` is version 13 and instructs the agent to inspect `usefulness`/JOIN/residual checks before lower-value detail and to stop deterministic navigation once sufficient evidence exists.
- Tool catalog contract version is 4.

## Intentionally unchanged

- evidence-common 0.23.2
- code-analyzer-core 0.44.23a5
- static-analysis-runner 0.10.25
- prepared-knowledge-runtime 0.1.0.post7
- knowledge-layer-core 0.61.0a32
- knowledge-reporting 0.18.0
- knowledge-control-plane 1.2.0a22
- aisl-contract 0.3.0b4

No second producer, second Knowledge Layer, multi-revision adapter, vector search, Gold hardcode or new JOIN inference was introduced.
