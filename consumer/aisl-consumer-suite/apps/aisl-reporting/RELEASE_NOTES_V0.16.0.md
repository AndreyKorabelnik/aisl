# aisl-reporting 0.16.0

## Storage and SQL reports over Knowledge API

- Added `observed-storage-usage-report/v1` over the Knowledge API projection.
- Migrated `sql-source-inventory-report/v1` from local KLC/DuckDB access to the revision-pinned Knowledge API source-inventory endpoint.
- SQL evidence references are taken only from published `evidence_refs`; unmapped fields remain explicit limitations.
- Both profiles select artifacts by model kind and capabilities and have no local database fallback.
