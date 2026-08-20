# knowledge-api 0.21.0 — canonical recursive SQL target-column lineage

`GET /api/knowledge/v1/systems/{system_id}/sql/target-column-lineage` now reads the canonical recursive lineage already materialized in the normal `sql-observed-data-usage` / workspace SQL knowledge artifact.

The obsolete dependency on the separate `sql-target-source-mapping` artifact and `common.sql-target-value-source-mapping` capability is removed. The endpoint delegates to the existing KLC `sql-target-column-lineage/v1` read query and preserves recursive paths, transformation paths, resolution statuses and scoped gaps without API-owned inference.

The public endpoint now also accepts `repo_id` and `lineage_status`, matching the existing Knowledge Assistant tool contract. This is an intentional incompatible replacement of the previous compact S2T response; backward compatibility is not retained.
