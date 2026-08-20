# AISL / Auto-analysis next-chat handover

Date: 2026-08-15
Status: **INCREMENTAL_REVISION_SNAPSHOT_AND_MULTICASE_ATTRIBUTE_EXTENSION_BLOCK_COMPLETE**

## Canonical architecture

```text
Formalized Sources
→ Knowledge Production (Core → Runner → KLC)
→ knowledge_execution_result/v2 / PublicationCandidate
→ validation + atomic publication
════════ publication boundary ════════
→ AISL immutable KnowledgeRevision snapshots / typed KnowledgeProducts
→ Prepared Knowledge Runtime / AISL API
→ Agent SDK / external agents
```

AISL is deterministic/evidence-backed published knowledge. It does not own source analysis, vector/embedding search, agent planning/memory or write-back reasoning.

## New completed block

Incremental producer reuse is now compatible with the one-pinned-revision consumer contract.

- Same-system prior-revision dependencies require explicit `base_revision_id`.
- Publication performs copy-on-write snapshot composition: unchanged exact base products are retained; products produced by the new execution replace their `source_materialization_id` owner slots.
- Retained bytes/digests are revalidated; no product rebuild or binary copy is required.
- Cross-system dependencies stay provenance only.
- Capabilities are computed from the final composed snapshot.
- No multi-revision read adapter or active/latest inference exists.

Real acceptance (`aisl-attribute-extension-final`):

- base revision `rev-1ef19edb4b8f99f927b30e38`
- composed revision `rev-1fed54320afb0632c144e098`
- 8 products / 44 capabilities
- `attribute-addition-plan/v1` profile v12: 17 tools, scope pinned to the composed revision

Multi-case relation usefulness acceptance passed for exact JOIN, proposed JOIN, collection, polymorphic ambiguity, probable direct reference and unresolved evidence. Scalar `BirthPlace.value` correctly bypasses relationship context and still resolves SQL target/insertion.

## Versions

- evidence-common 0.23.2
- code-analyzer-core 0.44.23a5
- static-analysis-runner 0.10.25
- prepared-knowledge-runtime 0.1.0.post7
- knowledge-layer-core 0.61.0a32
- knowledge-integration 0.1.10
- knowledge-api 0.30.11
- knowledge-reporting 0.18.0
- knowledge-control-plane 1.2.0a22
- aisl-contract 0.3.0b4

## Tests / acceptance

- AISL Contract: 45/45 PASS.
- Knowledge API: 94/94 PASS (terminal pytest log; container command wrapper remained alive after pytest completion).
- Knowledge Integration: 15/15 PASS.
- KLC unchanged in this block; latest full regression remains 252 PASS, 8 SKIPPED.
- Real base + incremental composed publication: PASS.
- One-revision 17-tool consumer profile: PASS.
- Multi-case consumer-only HTTP acceptance: PASS.

Final packaged-manifest/SHA results are recorded in the recovery package generated from this block.

## Next

P0 product work: consumer ergonomics trace analysis on `attribute-addition-plan/v1`. Measure tool selection, calls/context volume, JOIN visibility, uncertainty preservation and repeated deterministic navigation. Add a read projection only if trace evidence proves it useful.

Then: System Interactions as the next independent AISL knowledge domain.

## Parked

- independent UCP-91 external DeepSeek run until user resumes;
- vector DB / embeddings inside AISL;
- agent memory/planning/write-back inside AISL;
- universal graph/EAV/triple canonical storage;
- FI-002 and other parked scopes unless explicitly resumed;
- compatibility adapters / dual-read for superseded internal contracts.

## Recovery rule

In a new chat start from the recovery/canonical ZIP produced by this block and verify its SHA-256, module versions and manifests before changing code. Do not start from API 0.30.10 / AISL Contract 0.3.0b3 merely because they appear earlier in history.
