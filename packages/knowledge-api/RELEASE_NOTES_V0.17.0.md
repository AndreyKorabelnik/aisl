# knowledge-api 0.17.0

## Observed storage API

- Added revision-pinned read-only endpoints for observed storage accesses and gaps.
- Added typed response contracts and deterministic summary counts for reads, writes, storage kinds, resolution status and gaps.
- Publication validates the `observed-storage-usage/v1` artifact before activation.
- Existing SQL endpoints required no SQL-specific publication changes: SQL functions appeared from the published `common.sql*` capabilities.
- No local knowledge build, fallback or legacy single-DB route was introduced.
