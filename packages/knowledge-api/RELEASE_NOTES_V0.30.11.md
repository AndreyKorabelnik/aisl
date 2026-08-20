# knowledge-api 0.30.11

Adds explicit copy-on-write KnowledgeRevision snapshot publication for incremental producer results.

- `publish` / revision-create accepts optional `base_revision_id`.
- A same-system `external_knowledge_artifacts[]` dependency requires that exact base revision; active/latest is never guessed.
- The new immutable revision retains exact unchanged products from the base and replaces only product slots owned by materializations produced by the new execution.
- Retained artifact bytes/digests are revalidated and capabilities are derived from the final composed snapshot.
- Cross-system external dependencies remain provenance only and are not silently imported into the new system snapshot.
- Consumer reads remain pinned to one revision; no multi-revision read adapter was introduced.
- Catalog schema is intentionally replaced; pre-0.30.11 catalogs are rejected rather than migrated or dual-read.
- Packaging now requires `knowledge-integration==0.1.10`, matching the shipped attribute-addition profile v12.
