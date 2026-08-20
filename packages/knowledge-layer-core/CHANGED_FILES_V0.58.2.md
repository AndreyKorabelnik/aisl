# knowledge-layer-core 0.58.2 — legacy data-model Task/Suite removal

## Runtime changes

- Removed the one-repository compatibility builder `repository_builder.py` and its public export.
- Removed the hidden common data-model build from `build_suite_knowledge_layer`.
- Suite construction no longer consumes a `data-model` task and no longer publishes common/effective data-model capabilities.
- Full-fact JSONL artifacts are ingested directly and deterministically into `analysis_fact`, preserving task provenance without a common-model side effect.
- Updated suite tests and documentation for suite-only knowledge construction.

## Canonical replacement

Repository and effective data models are produced only through typed evidence and `knowledge_materialization_runtime/v1` materializations.

No compatibility alias, dual-write or hidden fallback was retained.
