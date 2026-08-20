# AISL Storage Mobility — Acceptance

Date: 2026-08-16  
Status: **AISL_STORAGE_MOBILITY_COMPLETE**

## Goal

Prove the runtime invariant **physical Artifact Store location is not semantic KnowledgeProduct/KnowledgeRevision identity**.

## Accepted design

Published immutable artifacts use logical content locators:

```text
aisl+sha256://<digest>
```

The filesystem Artifact Store root is runtime configuration. The catalog stores product/revision membership and content identities; it does not need to be rewritten when the filesystem root changes.

## Destructive E2E acceptance

Controlled mixed revision:

- observed `java-type-structure-evidence/v1`;
- derived `code-declared-data-model/v1` with exact dependency on the observed product.

Revision: `rev-a9eb627642530740ceed95fa`.

Sequence and result:

1. Publish mixed observed+derived revision to Artifact Store A: **PASS**.
2. Verify published physical members use `aisl+sha256://<digest>`: **PASS**.
3. Delete producer workspace: **PASS**.
4. Move the complete Artifact Store to a different filesystem root B: **PASS**.
5. Restart Knowledge API using the same SQLite catalog and only the new `artifact_store_path`: **PASS**.
6. Revision id unchanged: **PASS**.
7. Stored revision/product JSON unchanged: **PASS**.
8. Product ids/content fingerprints/member SHA-256 identities unchanged: **PASS**.
9. Exact observed read after relocation: **PASS**.
10. Exact derived read after relocation: **PASS**.
11. No semantic republication/catalog rewrite: **PASS**.
12. No second product/artifact registry or dual-read/write: **PASS**.

Validation snapshots are under `validation/aisl-storage-mobility-2026-08-16/`.

## Scope not claimed

- No object-store/HDFS backend implementation was added.
- No GC was implemented in this block.
- No compatibility migration is claimed for historical pre-0.33.0 revisions that stored absolute filesystem CAS URIs; backward compatibility was not required.
