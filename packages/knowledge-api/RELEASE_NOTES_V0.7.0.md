# knowledge-api 0.7.0

## Operational publication CLI

The CLI now exposes explicit commands:

- `knowledge-api serve`
- `knowledge-api validate`
- `knowledge-api publish`
- `knowledge-api system list|show|update|delete`
- `knowledge-api revision list|activate`

`publish` accepts local Knowledge Layer/report paths, computes artifact descriptors, reads provenance from a Knowledge Layer manifest, validates the DuckDB before catalog mutation, creates a missing system, publishes an immutable revision and activates it by default.

Revision identity is based on artifact content and stable provenance. Absolute paths, filenames, execution IDs and the activation flag do not create duplicate revisions.

## Administration

- `PATCH /api/knowledge/v1/systems/{system_id}` updates display name, description and metadata.
- Metadata uses merge semantics; a `null` value deletes a key.
- `POST /api/knowledge/v1/systems/{system_id}/revisions/{revision_id}/activate` supports rollback.
- `DELETE /api/knowledge/v1/systems/{system_id}` permanently removes a system and all revisions.
- CLI deletion requires explicit `--yes` confirmation.

## Validation

Focused contract/unit validation: 24 tests passed.
A real AT900 Knowledge Layer smoke verified validate, first publication, idempotent re-publication, system update and confirmed deletion. No deep platform regression was run by design.
