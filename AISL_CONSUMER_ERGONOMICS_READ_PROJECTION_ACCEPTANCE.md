# AISL consumer ergonomics read-projection acceptance

Date: 2026-08-15
Status: **CONSUMER_ERGONOMICS_READ_PROJECTION_BLOCK_COMPLETE**

## Architectural acceptance

The consumer path remains:

```text
one pinned KnowledgeRevision
→ existing typed data-model-attribute-extension-context/v1
→ thin Knowledge API selection/bounding projection
→ same capability-gated external tool
→ external agent
```

Accepted constraints:

- no producer/KLC re-run is required for already-published attribute-extension knowledge;
- the canonical detail endpoint remains the source of full read detail;
- the guidance endpoint creates no new relation/JOIN/business semantics;
- `usefulness` is copied from KLC and is not recomputed in API/Integration;
- a `confirmed` technical relationship can still have `ambiguity`, `probable` or `strongly_supported` consumer usefulness;
- gaps and truncation remain visible;
- the external tool name/count is unchanged and the revision remains pinned.

## Compactness / visibility acceptance

Deterministic API contract fixtures representing the two critical shapes show:

| Case | Full canonical response | Guidance response | Reduction | Semantic guard |
|---|---:|---:|---:|---|
| exact observed JOIN | 3240 B | 2687 B | 17.1% | `confirmed` stays `confirmed`; exact predicate/relevance visible |
| polymorphic collection | 3571 B | 2170 B | 39.2% | technical confidence remains `confirmed`, usefulness remains `ambiguity` |

The exact case keeps the observed SQL predicate, `relationship_relevance`, storage-reference observation and provenance. The polymorphic case keeps candidate targets, residual subtype/representation check and diagnostic.

A heavy synthetic contract case proves bounded output: 20 JOIN examples are presented as 6 with explicit truncation; 10 column pairs are bounded with truncation metadata; 30 gaps are presented as 20 with explicit truncation.

## Test acceptance

- Knowledge Integration 0.1.11: **15/15 PASS**.
- Knowledge API 0.30.12: **96/96 PASS**, executed as two complete batches: 60/60 + 36/36.
- Focused final contract set: **30/30 PASS**.
- OpenAPI regeneration/parity: **PASS**.
- An earlier monolithic API run reached late-suite progress without failures but was terminated by wrapper timeout; it is not counted as PASS. Complete split execution is the authoritative result.

## Limitation / unresolved acceptance item

The recovery package did not preserve a live catalog for `rev-1fed54320afb0632c144e098` or a captured post-change external-agent trace. Therefore this block does **not** claim reduced real LLM tool-call count or improved final-answer quality yet. The next acceptance step is a real external-agent trace against the existing published knowledge using API 0.30.12 + Integration 0.1.11; production knowledge should not be rebuilt merely for that test.
