# knowledge-layer-core 0.59.48

## Purpose
Make KLC the single owner of read/query semantics for its Prepared Knowledge marts.

## Changes
- Added `EffectiveDataModelReadService` for `effective-data-model/v1` marts.
- Added `DataModelLineageReadService` for current cross-artifact lineage marts.
- Added `ObservedStorageUsageReadService` for observed-storage usage marts.
- Moved DuckDB table/column knowledge for these read paths out of Knowledge API and into KLC.
- Existing materialization schemas and Producer behavior are unchanged.

## Non-changes
- No Core or Runner changes.
- No rematerialization requirement.
- No new Knowledge Layer semantics.
- No compatibility/dual-read path.
