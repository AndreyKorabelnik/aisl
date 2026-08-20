# AISL Multi-file Published Persistence — Acceptance

Date: 2026-08-16  
Status: **AISL_MULTIFILE_PUBLISHED_PERSISTENCE_COMPLETE**

## Goal

Prove the AISL persistence boundary for a second, genuinely multi-file Core observed product and only then generalize the physical representation of a published `KnowledgeProduct`.

Real observed product: Core `sql-analysis/v1` over `datamart_profile_fl`.

## Accepted physical contract

A semantic `KnowledgeProduct` has one semantic identity and one or more immutable physical members addressed by unique product-local roles:

```text
KnowledgeProduct
  origin_kind
  producer / producer_contract
  product_slot_id
  content identity
  dependencies
  physical_artifacts[]
    - role
    - uri
    - sha256
    - byte_size
    - media_type
```

The physical member list is not a second catalog. AISL Catalog remains the source of truth for revision membership; AISL Artifact Store owns immutable bytes.

The previous mutually exclusive internal fields `database`, `manifest`, and `observed_artifact` were removed rather than retained as compatibility paths.

## Real SQL package

Current Core produced:

- product id: `sql_analysis_2223a9945b5214605c10a320`;
- schema: `sql-analysis/v1`;
- producer status: **partial**;
- SQL units: **306**;
- SQL files scanned: **480**;
- SQL statements: **475**;
- lineage gaps: **70**;
- fact shards: **19**;
- total physical members: **22** = descriptor + manifest + coverage + 19 fact shards.

The old documentation number of 17 shards is not used as current truth; the actual current runtime package contained 19 shards.

## Publication and destructive consumer-autonomy acceptance

Published system: `datamart-profile-fl`  
Revision: `rev-3156d56a22184e6a609bc36e`

Acceptance:

1. Core produced the real partial `sql-analysis/v1` package: **PASS**.
2. Publication validated descriptor/manifest/coverage/shard identities before catalog visibility: **PASS**.
3. All 22 physical members were imported/finalized in AISL-managed content-addressed storage: **PASS**.
4. One observed `KnowledgeProduct` contains all 22 role-addressed members: **PASS**.
5. Exact `sql_statement` read before producer deletion: **PASS**.
6. Exact `sql_join_edge` read before producer deletion: **PASS**.
7. The source repository was physically deleted: **PASS**.
8. The complete Core producer output was physically deleted: **PASS**.
9. Exact `sql_statement` read from pinned revision after deletion: **PASS**.
10. Exact `sql_join_edge` read from pinned revision after deletion: **PASS**.
11. Producer status remains `partial`; 70 lineage gaps remain explicit: **PASS**.

Post-delete read snapshots are retained under `validation/aisl-multifile-persistence-2026-08-16/`.

## Evidence-discipline invariant discovered by the real run

A valid Core observed artifact may be `partial`. Publication therefore accepts observed status `completed` or `partial` when the product passes its structural/package validation; `failed` is not publishable.

Publication does **not** promote `partial` to `completed`, and does not hide gaps/diagnostics.

## Scope deliberately not claimed

- No claim that all Core evidence contracts have been individually acceptance-tested.
- No storage relocation/backend-mobility acceptance yet.
- No reachability-based GC yet.
- No Core analyzer, Runner or KLC semantic changes were required.
