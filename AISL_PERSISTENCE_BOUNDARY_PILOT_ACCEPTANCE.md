# AISL Persistence Boundary Pilot — Acceptance

Date: 2026-08-16
Status: **AISL_PERSISTENCE_BOUNDARY_PILOT_COMPLETE**

## Goal

Prove that AISL, rather than a producer workspace, owns the durable lifecycle of published immutable analysis products while Core/KLC retain semantic ownership.

Pilot observed product: `java-type-structure-evidence/v1` produced by Core.
Pilot derived product: `code-declared-data-model/v1` produced by KLC.

## Accepted architecture

- Core owns observed evidence semantics and analyzer contracts.
- KLC owns derivation semantics and native derived schemas.
- Runner/KCP own production execution lifecycle.
- AISL Catalog owns logical published revision/product membership and exact dependencies.
- AISL Artifact Store owns durable immutable published bytes.
- Physical artifact location is not semantic product identity.
- Prepared Runtime / Knowledge API serve published products without production components.

## Real acceptance

Fresh Runner production V1 and V2 each produced one Core observed product and one KLC derived product.

R1: `rev-ca39be021ceb0824d1b7fc5f`

- observed: `java_type_structure_37e029f6a95d4594283f9cce`
- derived: `knowledge_artifact_8f92532e7a65b921acad`
- derived exact dependency points to the observed product: PASS
- published observed bytes are in AISL Artifact Store: PASS
- published derived DuckDB + manifest are in AISL Artifact Store: PASS
- exact observed and derived reads before producer deletion: PASS
- source repository and complete Runner output were deleted: PASS
- exact observed and derived reads after producer deletion: PASS

R2: `rev-a1c957654c74d11dc2e6dcf7`

- changed observed product: `java_type_structure_42d7a8eef790a1821a3653eb`
- rebuilt derived product: `knowledge_artifact_43755eda1917a4a7032c`
- C2 exact dependency points to A2: PASS
- A1/C1 are not retained in R2: PASS
- R2 reads after deleting the second producer environment: PASS
- R1 remains queryable after both producer environments are deleted: PASS

A deliberately stale COW proposal that replaces observed A1 with A2 while retaining derived C1 is rejected by publication with `revision_exact_dependency_unresolved`: PASS (contract test).

## Consumer autonomy proved

After publication the real source repositories and Runner output trees were removed. Reads required only the AISL catalog, AISL Artifact Store and consumer runtime/API. Core, Runner and KLC were not invoked for those reads.

## Scope deliberately limited

The pilot supports one self-contained observed Core product. Multi-file/sharded Core artifacts are the next persistence step and are not silently declared supported.

GC, object/HDFS storage backends and storage-location migration are not part of this pilot.
