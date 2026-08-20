# AISL Published Persistence Pilot — Acceptance

Date: 2026-08-16  
Status: **PUBLISHED_PERSISTENCE_PILOT_COMPLETE**

## Goal

Validate the architectural direction that AISL owns the durable lifecycle of all **published** immutable KnowledgeProducts while Core/KLC retain semantic ownership.

Pilot product: `java-type-structure-evidence/v1` produced by Core.

## Accepted ownership boundary

```text
Core                         semantic owner / producer of observed evidence
KLC                          semantic owner / producer of derived knowledge
Runner / KCP                 production execution lifecycle
publication                  validation + durable lifecycle handoff
════════════════════════════════════════════════════════════════════
AISL Catalog                 revisions, membership, dependencies, capabilities
AISL Artifact Store          durable immutable published bytes
Prepared Runtime / API       consumer read boundary
Agents                       consumers
```

Publication transfers durable lifecycle responsibility, not semantic ownership.
Physical artifact location/filename is not semantic product identity.

## Real runtime vertical slice

The final release acceptance used a real Java repository and the official production path:

`source → Core 0.44.23a5 → Runner 0.10.25 → KLC 0.61.0a32 → knowledge_execution_result/v2 → Knowledge API publication`.

Execution plan contained exactly:

1. Core `java-type-structure-analyzer`;
2. KLC `code-declared-data-model`.

### Revision R1

- revision: `rev-7295d3fa8a58c987a6026450`
- observed product: `java_type_structure_c8ed285ee4362639bf04ef13`
- derived product: `knowledge_artifact_9dd49c9e1a6ae998a8db`
- derived exact dependency: observed product above
- all published observed/database/manifest/execution-result bytes resolved to AISL CAS paths of the form `artifact-store/sha256/<prefix>/<sha256>/blob`.

After successful publication the source repository and complete Runner output directory were physically deleted. The same pinned revision still returned:

- observed `type_declaration` exact read: **PASS**;
- derived `declared_object` exact read: **PASS**;
- revision read: **PASS**.

This is the principal consumer-autonomy / durable-persistence acceptance.

### Revision R2 — real COW

Java was changed by adding `citizenship`, then a new official Core+KLC execution was published with R1 as explicit base.

- revision: `rev-059d40e185d30e1f040b00b8`
- new observed product: `java_type_structure_f79bf738e3fed9633ea06f65`
- new derived product: `knowledge_artifact_8b7d77188ffce0c157e6`
- new derived exact dependency: new observed product above
- R1 products are absent from the R2 snapshot;
- exact observed `citizenship` field read: **PASS**.

After deleting the R2 source repository and complete Runner output directory:

- R1 observed + derived reads: **PASS**;
- R2 observed + derived reads: **PASS**;
- both revision reads: **PASS**.

## Exact dependency integrity

A targeted publication contract test additionally proves:

- `A2 + stale C1(depends exactly on A1)` → publication **REJECT**;
- `A2 + C2(depends exactly on A2)` → publication **PASS**.

Publisher does not infer how to rebuild stale products; it only rejects an inconsistent immutable snapshot.

## Artifact Store

Pilot filesystem backend:

- content addressed by SHA-256;
- physical layout `sha256/<prefix>/<sha256>/blob`;
- import uses copy → fsync → SHA verification → atomic finalize;
- no hardlink contract;
- same bytes from different filenames deduplicate to one blob;
- corrupt existing blob is rejected;
- original filename is descriptor metadata only.

CAS is not the Catalog. Catalog revision membership remains the logical source of truth.

## Product model

One KnowledgeProduct model remains in use.

- `origin_kind=observed` for Core-owned published evidence;
- `origin_kind=derived` for KLC-owned published knowledge;
- producer provenance is explicit;
- exact product dependencies are explicit;
- item semantic quality remains a separate axis from product origin.

No `ObservedProduct`, universal EAV, graph, triple store or second registry was introduced.

## Consumer/runtime result

`java-type-structure-evidence/v1` has a native exact reader through the existing universal KnowledgeItem API.
Derived DuckDB readers now open the explicitly published database and manifest artifacts; they do not infer database type or manifest location from producer-side filenames/directories.

The persistence pilot exposed and removed two hidden consumer assumptions:

1. DuckDB recognition by filename suffix;
2. accidental use of a sibling producer-side manifest rather than the published manifest.

## Tests

- Knowledge API 0.31.0: **108/108 PASS** (`19 + 26 + 17 + 29 + 17`, completed groups only).
- Prepared Knowledge Runtime 0.1.0.post8: **8/8 PASS**.
- Knowledge Integration 0.1.15: **19/19 PASS**.
- AISL Contract 0.3.0b5: **46/46 PASS**.
- Knowledge Layer Core 0.61.0a32: **252 PASS, 8 SKIPPED** (`108 + 33 + 69 + 42`, skips `7 + 1`).
- Knowledge Control Plane 1.2.0a23: **95/95 PASS**.
- final real destructive R1 acceptance: **PASS**.
- final real COW R2 acceptance: **PASS**.

Monolithic/partial test invocations terminated by the external wrapper are not counted as PASS.

## Not yet claimed

- generic publication of all Core evidence types;
- multi-file / descriptor+payload Core artifact packages;
- storage backend mobility acceptance;
- artifact garbage collection;
- zero orphan CAS blobs after a crash between import and catalog commit;
- catalog SQLite normalization;
- a generic reader registry beyond demonstrated reuse need.

The explicit pilot allow-list currently admits only `java-type-structure-evidence/v1` as a Core observed product.
