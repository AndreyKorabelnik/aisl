# AISL Persistence Pilot — Next Chat Handover

Status: **AISL_PERSISTENCE_BOUNDARY_PILOT_COMPLETE**
Date: 2026-08-16

Start from the canonical ZIP/SHA recorded in the recovery package. Do not return to the pre-pilot reference-data baseline.

## Completed

- AISL Catalog + filesystem AISL Artifact Store now own the durable lifecycle of published pilot products.
- Core observed `java-type-structure-evidence/v1` is a first-class observed KnowledgeProduct.
- KLC `code-declared-data-model/v1` remains a derived KnowledgeProduct.
- Mixed observed+derived exact dependencies are retained in one immutable revision.
- Physical producer workspace can be deleted after publication; exact observed/derived reads remain available.
- COW replacement rejects stale exact dependencies.
- No Core/KLC semantic changes were required.

Real revisions:
- R1 `rev-ca39be021ceb0824d1b7fc5f`
- R2 `rev-a1c957654c74d11dc2e6dcf7`

## Next recommended block

Generalize physical artifact packaging beyond the single-file observed pilot using one real descriptor+payload/sharded Core evidence product. Prefer a product already needed by consumers. The goal is a generic `physical_artifacts[]`/package import contract proven by more than one physical shape, not a new semantic model.

After multi-file package acceptance, validate storage mobility (`artifact identity != location`). GC remains later.

## Do not do next

- do not normalize Knowledge API SQLite just because products now span Core/KLC;
- do not publish Core caches/temp artifacts;
- do not create an ObservedProduct parallel hierarchy;
- do not add universal reader registry unless a second observed physical/schema case proves the abstraction useful;
- do not implement GC before package/import semantics stabilize.
