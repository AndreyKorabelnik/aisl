# Change report — incremental AISL revision snapshots and multi-case attribute extension

Date: 2026-08-15

## Changed modules

### knowledge-api 0.30.11

- Added optional `base_revision_id` to revision publication and persisted revision metadata.
- Added copy-on-write snapshot composition at publication boundary.
- Same-system prior-revision dependencies now require the exact explicit base revision; no active/latest fallback.
- Retained artifacts are identity/digest revalidated.
- Produced products replace base products by official `source_materialization_id` owner slot.
- Final capabilities are calculated from the composed product set.
- Cross-system external dependencies are not automatically retained.
- Pre-0.30.11 catalog schema is rejected; no migration/dual-read adapter was added.
- CLI `publish` accepts `--base-revision-id`.
- OpenAPI regenerated for 0.30.11.
- Packaging dependency aligned from stale `knowledge-integration==0.1.8` to canonical `0.1.10`.

### aisl-contract 0.3.0b4

- Added optional `KnowledgeRevision.base_revision_id`.
- Added schema support and invariants.
- Added ADR-011 for copy-on-write immutable revision snapshots.
- Preserved the one-pinned-revision consumer contract.

## Intentionally unchanged

- Core 0.44.23a5
- Runner 0.10.25
- KLC 0.61.0a32
- Prepared Runtime 0.1.0.post7
- Knowledge Integration 0.1.10 implementation/profile
- KCP 1.2.0a22

No second product composer, no multi-revision query adapter, no dual-read catalog compatibility and no Gold-specific behavior were introduced.
