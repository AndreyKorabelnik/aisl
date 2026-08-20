# knowledge-layer-core 0.24.0

Adds the complete typed field catalog required by user-requested artifact builders.

## Changes

- `DataModelQueryService.list_fields()` returns all effective model fields in one typed query and avoids an N+1 query per object.
- Field records now preserve `object_id`, `object_fqcn` and `repo_id` together with exact evidence.
- Workspace query-surface selection is based on canonical scope/capability metadata (`scope_type=workspace` and `common.effective-model`), not on the UCP/TSA-specific `framework.tsa` capability.
- No arbitrary SQL, business classification, conceptual synthesis or LLM behavior was added to KLC.
