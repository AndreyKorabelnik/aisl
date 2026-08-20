# knowledge-layer-core 0.25.0

Iteration 20 imports generic storage-record evidence produced by code-analyzer-core 0.39.0.

## Changes

- Workspace schema upgraded to `workspace_data_model/v14`.
- Repository evidence contract accepts `storage_alias_assignment_observation`, `storage_record_observation` and `storage_reference_observation`.
- Added facts-only views `v_storage_records` and `v_storage_references`.
- Views preserve owner operation, source field, target alias, physical storage-key field and expression, binding path and provenance.
- Physical encoding remains explicitly delegated downstream; KLC performs no alias normalization, separator insertion, SQL generation or join verdict.
- Older repository evidence remains compatible because the new fact files are optional unless declared/present.

Public relationship JSON is intentionally unchanged in this release.
