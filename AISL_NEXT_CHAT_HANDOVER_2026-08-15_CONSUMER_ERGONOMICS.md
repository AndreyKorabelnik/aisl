# AISL / Auto-analysis next-chat handover — consumer ergonomics read projection

Date: 2026-08-15
Status: **CONSUMER_ERGONOMICS_READ_PROJECTION_BLOCK_COMPLETE**

## Canonical architecture

```text
Formalized Sources
→ Knowledge Production (Core → Runner → KLC)
→ knowledge_execution_result/v2 / PublicationCandidate
→ validation + atomic publication
════════ publication boundary ════════
→ AISL immutable KnowledgeRevision snapshots / typed KnowledgeProducts
→ Prepared Knowledge Runtime / Knowledge API
→ consumer-only Agent SDK / external agents
```

AISL remains deterministic/evidence-backed published knowledge. It is not a mathematical proof system and does not own vector/embedding search, agent planning/memory or write-back reasoning.

## Completed sub-block

The existing external tool `get_data_model_attribute_extension_context` no longer receives the full canonical attribute-extension context by default. Knowledge API 0.30.12 exposes a thin compact `attribute-extension-guidance` projection and Knowledge Integration 0.1.11 binds the same tool to it.

The projection:

- copies KLC-owned `usefulness` verbatim and surfaces it early;
- exposes exact-vs-analog JOIN relevance/predicate, storage observations, key/reference expressions and residual checks;
- preserves technical confidence, ambiguity, unresolved/gaps and provenance;
- removes occurrence-id/empty-section noise and bounds heavy collections with explicit truncation;
- leaves the canonical `/data-model/attribute-extension-context` read unchanged for exact detail;
- performs no semantic derivation or JOIN/business inference.

Tool count is unchanged. `attribute-addition-plan/v1` is profile version 13 and still uses one pinned revision.

## Existing real AISL base for consumer acceptance

Recovery from the preceding block records:

- base revision: `rev-1ef19edb4b8f99f927b30e38`
- composed revision: `rev-1fed54320afb0632c144e098`
- 8 products / 44 capabilities
- previous profile v12: 17 tools, one pinned revision

The new consumer projection can read already-published `data-model-attribute-extension-context/v1`; do not rerun Core/Runner/KLC solely to test consumer ergonomics.

## Versions

- evidence-common 0.23.2
- code-analyzer-core 0.44.23a5
- static-analysis-runner 0.10.25
- prepared-knowledge-runtime 0.1.0.post7
- knowledge-layer-core 0.61.0a32
- knowledge-integration 0.1.11
- knowledge-api 0.30.12
- knowledge-reporting 0.18.0
- knowledge-control-plane 1.2.0a22
- aisl-contract 0.3.0b4

## Tests / acceptance

- Knowledge Integration: 15/15 PASS.
- Knowledge API: 96/96 PASS as complete split execution 60/60 + 36/36.
- Final focused contract set: 30/30 PASS.
- OpenAPI parity: PASS.
- Contract fixture compactness: exact -17.1%; polymorphic -39.2%.
- Exact stays confirmed; polymorphic technical confidence stays confirmed while usefulness stays ambiguity.

A monolithic API attempt was terminated by wrapper timeout late in the run and is not claimed as PASS; the complete split execution is authoritative.

## Unresolved / next acceptance

No post-change real external-agent trace is present in the recovery environment. Therefore no claim is made yet about real LLM call-count reduction or final-answer quality.

Next: run representative external-agent attribute-addition requests against the existing published knowledge with API 0.30.12 + Integration 0.1.11. Measure tool selection/order, call count, context volume, JOIN visibility, uncertainty preservation and final answer concision. Change read ergonomics again only if the trace proves a concrete remaining issue.

After that, start System Interactions as the next independent AISL knowledge domain.

## Parked

Do not automatically resume UCP-91 external DeepSeek, FI-002, vector/embedding retrieval inside AISL, portfolio topology, universal graph, agent memory/planning or compatibility cleanup without a proven duplicate.
