# AISL Storage Mobility — Next Chat Handover

Date: 2026-08-16  
Status: **AISL_STORAGE_MOBILITY_COMPLETE**

## Completed

- Published bytes are addressed in catalog state by `aisl+sha256://<digest>`, not absolute filesystem roots.
- Artifact Store root is runtime storage configuration.
- Mixed observed+derived revision survives complete filesystem root relocation with no semantic republication or catalog rewrite.
- Producer environment remains absent.
- Exact observed and derived reads pass after relocation.
- Product/revision semantic identities remain unchanged.

## Next persistence lifecycle block

**Reachability-based Artifact Store GC.**

Requirements before implementation:

1. catalog/revision membership remains the only source of reachability truth;
2. GC must not become part of publication correctness;
3. blobs referenced by any retained revision must never be deleted;
4. unreferenced/orphan blobs may become GC candidates after a safe policy/grace period;
5. no second registry, refcount dual-write or SQLite normalization unless a concrete operational need is proven;
6. crash-created orphan blobs are operational debt, not visible knowledge.

First research the current delete-system/revision-retention semantics and determine the smallest deterministic reachability scan from existing catalog JSON. Do not implement GC by guessing retention policy.

Parked scope remains parked.
