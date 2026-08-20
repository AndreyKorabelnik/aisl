# AISL System Interactions consumer guidance — change report

Date: 2026-08-15  
Status: **SYSTEM_INTERACTIONS_AISL_REAL_CONSUMER_GUIDANCE_BLOCK_COMPLETE**

## Runtime changes

### knowledge-api 0.30.13

- Added `system-interaction-guidance/v1` compact read projection.
- Added `GET /api/knowledge/v1/systems/{system_id}/interactions/{interaction_id}/guidance`.
- Exact grouping only by published `interaction_id` / `boundary_interaction_id`.
- Preserves KLC `match_status`, `confidence`, match basis, endpoints and provenance.
- Bounded execution contexts and field contracts include explicit source totals / presented counts / truncation.
- Optional field-contract product absence is explicit `not_available`.
- Unknown exact interaction returns `system_interaction_not_found`; no fallback matching.
- Canonical raw detail endpoints remain unchanged.

### knowledge-integration 0.1.12

- Added capability-gated `get_system_interaction_context` tool.
- Updated `system-interactions/v1` retrieval policy to profile v2.
- Common path is now `list_system_interactions → get_system_interaction_context`.
- Detailed boundary/context/contract tools remain drill-down/continuation tools.
- Tool catalog contract version: 5.

## Unchanged producer/runtime owners

- evidence-common 0.23.2;
- code-analyzer-core 0.44.23a5;
- static-analysis-runner 0.10.25;
- prepared-knowledge-runtime 0.1.0.post7;
- knowledge-layer-core 0.61.0a32;
- knowledge-reporting 0.18.0;
- knowledge-control-plane 1.2.0a22;
- aisl-contract 0.3.0b4.

No Core evidence extractor, Runner plan semantics, KLC interaction matching/materialization or publication ownership was changed.

## Why the change is generic

The consumer friction was identified from the typed contract itself: a selected `system_interaction` already referenced an exact matched boundary interaction, but the external tool catalog did not expose a compact exact read and raw detail duplicated large evidence payloads. The fix therefore projects already-published typed rows; it contains no repository names, paths, Gold targets or application-specific rules.

## Compatibility

No compatibility adapter, dual-read, dual-write or legacy endpoint was introduced. Existing canonical detailed endpoints stay because they are still the authoritative drill-down surface, not as a compatibility path.
