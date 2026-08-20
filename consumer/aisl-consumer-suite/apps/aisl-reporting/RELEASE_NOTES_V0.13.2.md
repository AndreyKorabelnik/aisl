# aisl-reporting 0.13.2

## Exact FDP case reporting

- Adapted the Foreign Data Persistence report to the breaking `storage_field_path_pair` case contract published by knowledge-layer-core 0.53.4.
- Removed table-level mechanical cases from report evidence. Table aggregation is retained only as `storage_summaries` and is explicitly marked as non-proof.
- A report case now contains one physical storage field, one source path, and one access path.
- Added deterministic case selection for large exact-case catalogs.
- All confirmed exact cases are always retained; the remaining budget is filled with selected-path pairs, other connected cases, and unmatched background cases.
- Added explicit case-catalog completeness metadata and omitted-case counts.
- The renderer prompt now prohibits combining fields or paths from different exact cases into one end-to-end claim.
- No business FDP verdict or risk decision is assigned by the reporting layer.
