# knowledge-layer-core 0.59.42

Legacy Cleanup Block 4 removes four confirmed dead compatibility surfaces from the current Knowledge Layer.

## Removed

- `legacy_fallback_used=False` from logical/physical mapping validation.
- `legacy_conceptual_model_consumed=False` from effective data-model validation and manifest metadata.
- unused public alias `COMPATIBILITY_SCHEMA_VERSION = workspace_data_model/v13`.
- obsolete private `_export_table_jsonl(..., fetch_size=1000)` compatibility parameter.

No replacement aliases, default injection, dual-read, adapters, or compatibility branches were introduced.

## Preserved

- current validation checks that assert real model invariants;
- deterministic native DuckDB JSONL export;
- uncertainty, gaps, ambiguity and normal analysis fallbacks;
- current typed materialization contracts.

Historical release and validation artifacts are retained as provenance and may still contain the old field names.
