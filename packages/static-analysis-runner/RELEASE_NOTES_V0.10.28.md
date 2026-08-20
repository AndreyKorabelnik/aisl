# static-analysis-runner 0.10.28

## Optional internal knowledge enrichment

- Extends the canonical knowledge product catalog with `optional_internal_materializations` alongside existing required internal materializations.
- Keeps the requested public knowledge product executable when an optional internal runtime/input is unavailable; omission is explicit through `optional_internal_materialization_skipped` diagnostics and no fallback knowledge is invented.
- Activates an optional internal chain only from an explicitly requested knowledge item whose `include_optional_sources` option is enabled. Implicit dependency selection does not silently broaden execution.
- Preserves required-vs-optional provenance in the technical plan (`execution_requirement`, `required_by`, `optional_by`, `selection_origin`).
- `code-declared-data-model` now optionally enriches with the existing `logical-storage-mapping` materialization; its existing required dependency on `model-storage-semantics` is resolved through the same canonical materialization catalog.
- Core remains the only owner/producer of observed evidence and KLC remains the only owner of these derived storage semantics. No analyzer, materializer, adapter, dual-read or second planner is introduced.
