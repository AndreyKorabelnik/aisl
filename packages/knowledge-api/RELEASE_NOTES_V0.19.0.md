# knowledge-api 0.19.0 — compact ultimate S2T

## Purpose

Make `GET /api/knowledge/v1/systems/{system_id}/sql/target-column-lineage` the compact product S2T surface backed by canonical KLC value-origin knowledge rather than raw SQL recursive lineage.

## Contract changes

- Primary target-column lineage response is now `target-source-mapping/v1`.
- One response is grouped by target column and contains only:
  - target column;
  - ultimate `relation + column + status` sources;
  - mapping status;
  - source/dependency counts.
- Default limit is 500 so the real `epk_client` mapping fits in one call.
- `storage_identity` and `reference_key` KLC origins are not emitted as primary sources; they contribute to `dependency_count`.
- Detailed semantic lineage/provenance is available through `/data-model/lineage`, now backed by `cross-artifact-data-model-mapping/v6` (`data-model-lineage-query/v2`).
- The primary S2T endpoint requires `common.value-origin-physical-lineage`; raw SQL-only lineage artifacts no longer satisfy it.
- API performs no producer traversal, value/control inference, or placeholder resolution.
- No compatibility adapter for the former heavy target-column payload is retained.

## Real epk_client validation

Using KLC 0.59.23 real cross-artifact output:
- HTTP status: 200;
- one default call for `custom_b2c_profile_fl.epk_client` returns 90 target mappings;
- 86 mappings have ultimate sources; 4 technical/generated mappings have no semantic source;
- compact response size: 55.7 KB;
- `epk_id` exposes only current/history `Individual.id` as primary sources and reports 26 storage dependencies via `dependency_count`;
- `active_flag` resolves to current/history `Individual.endDate`;
- `last_name` resolves to current/history `IndividualName.surname`;
- display spelling such as `pon_managerCode` / `managerCode` is preserved;
- unresolved schema placeholders remain verbatim and produce `partial` mapping status.

HTTP payload vs supplied Gold, comparing exact target + source table + source column while ignoring schema: **113/132** rows. This exactly matches KLC validation; the API projection loses no established mappings. The remaining 19 rows are previously classified current-SQL/PDM vs Gold differences.
