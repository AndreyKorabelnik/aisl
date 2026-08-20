# AISL Multi-file Persistence — Next Chat Handover

Date: 2026-08-16  
Status: **AISL_MULTIFILE_PUBLISHED_PERSISTENCE_COMPLETE**

Start from the canonical ZIP/SHA recorded in the recovery package. Do not return to the single-file persistence pilot baseline.

## Completed

- AISL published persistence now has two proved observed physical shapes:
  - single-file `java-type-structure-evidence/v1`;
  - real multi-file/sharded `sql-analysis/v1`.
- One semantic `KnowledgeProduct` now uses generic role-addressed `physical_artifacts[]`.
- Old KLC/single-file physical shape fields were removed, not adapted.
- Real SQL package: descriptor + manifest + coverage + 19 fact shards = 22 members.
- Real partial observed product is preserved as partial with 70 lineage gaps.
- Source and complete Core output can be deleted after publication; exact SQL statement/JOIN reads remain available from AISL Catalog + Artifact Store.
- Core/Runner/KLC/KCP semantics were unchanged.

Real revision: `rev-3156d56a22184e6a609bc36e`.

## Next recommended block — storage mobility

Prove `physical location != semantic product identity` at runtime:

1. start from an already published revision/product;
2. move or migrate AISL Artifact Store bytes to a different physical root/backend locator;
3. update only physical storage resolution/configuration as required;
4. do **not** republish semantic KnowledgeProduct/KnowledgeRevision merely because bytes moved, if the current catalog/storage design permits this cleanly;
5. prove exact observed and derived reads remain PASS;
6. prove product/revision semantic identities are unchanged.

Research the smallest change first. Do not introduce object/HDFS infrastructure just to prove the invariant; a filesystem-root relocation is sufficient for the first acceptance.

## After mobility

Reachability-based GC is the next persistence lifecycle block. It is not required for publication correctness and should not be implemented before storage mobility semantics are stable.

## Do not do next

- do not normalize Knowledge API SQLite without an operationally demonstrated need;
- do not publish Core caches/temp/failed artifacts;
- do not add a second product/artifact registry;
- do not add dual-read/dual-write or compatibility fields for the removed physical shape;
- do not create universal graph/EAV/triples;
- do not resume parked UCP-91/FI-002/vector/portfolio/agent-memory work automatically.
