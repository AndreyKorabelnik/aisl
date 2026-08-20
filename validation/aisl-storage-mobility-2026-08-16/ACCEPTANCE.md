# AISL Storage Mobility Acceptance — 2026-08-16

Status: **PASS**

Controlled destructive E2E acceptance using one observed Core-style `java-type-structure-evidence/v1` product and one derived KLC-style `code-declared-data-model/v1` product.

Sequence:

1. Publish mixed observed + derived revision into AISL Catalog + filesystem Artifact Store A.
2. Confirm all published physical members use backend-root-independent `aisl+sha256://<digest>` locators.
3. Delete producer workspace.
4. Move the whole AISL Artifact Store directory from root A to a different filesystem root B.
5. Restart Knowledge API using the same SQLite catalog and only the new Artifact Store root configuration.
6. Read the exact same pinned revision.
7. Read one exact observed item and one exact derived item.

Accepted invariants:

- KnowledgeRevision id unchanged: PASS.
- KnowledgeProduct ids/content fingerprints unchanged: PASS.
- Stored revision JSON unchanged before/after relocation: PASS.
- Producer workspace remains absent: PASS.
- Old Artifact Store root absent: PASS.
- Observed exact read after relocation: PASS.
- Derived exact read after relocation: PASS.
- No semantic republication/catalog rewrite was performed: PASS.
- No second registry or dual-read/dual-write was introduced: PASS.

The filesystem root is runtime storage configuration. Published catalog state addresses immutable bytes by content digest rather than absolute filesystem path.
