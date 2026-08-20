# knowledge-api 0.28.0

## Purpose
Restore Knowledge API as a thin HTTP/read boundary over KLC-owned Prepared Knowledge query semantics.

## Changes
- `effective_data_model_query.py` delegates mart reads to KLC `EffectiveDataModelReadService`.
- `data_model_lineage_query.py` delegates mart reads to KLC `DataModelLineageReadService`.
- `storage_usage_query.py` delegates mart reads to KLC `ObservedStorageUsageReadService`.
- Knowledge API retains artifact/revision selection, path-keyed reader caching, HTTP/Pydantic projection and publication registry ownership.
- Added structural guard preventing direct DuckDB/KLC-mart SQL from returning to Knowledge API.

## Non-changes
- HTTP response contracts remain unchanged.
- Publication registry remains Knowledge API-owned SQLite.
- No Producer fallback, rematerialization, or second Knowledge Layer.
