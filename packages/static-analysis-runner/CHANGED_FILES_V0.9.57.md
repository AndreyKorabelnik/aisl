# static-analysis-runner 0.9.57 — legacy data-model Task/Suite removal

## Runtime changes

- Removed the `data-model` task and suite from the Runner registry and built-in examples.
- Removed repository-level Knowledge Layer construction from `run_repository_analysis`.
- Removed workspace profile mode and the profile-specific workspace data-model builder.
- Repository profile execution now rejects `repository-data-model-static` and `repository-system-data-model` and directs callers to the generic `knowledge-execute` route.
- Repository and workspace Task/Suite orchestration remains only for scenarios that do not yet have complete typed evidence/materialization contracts.
- Removed obsolete data-model and workspace example scripts.

## Canonical replacement

Data-model products are executed through:

`typed Java/PDM evidence -> knowledge execution plan -> knowledge-execute -> KLC materializations`

The confirmed materializations are `code-declared-data-model`, `physical-model`, `logical-physical-mapping` and `effective-data-model`.

No compatibility adapter, alias, dual-write or hidden fallback was added.
