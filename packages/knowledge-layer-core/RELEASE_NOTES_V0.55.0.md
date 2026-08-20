# Release Notes — knowledge-layer-core 0.55.0

Adds the second fully generic evidence-to-knowledge vertical path.

## Added

- `logical-physical-model-mapping/v1` DuckDB schema and deterministic builder.
- KLC-owned `logical-physical-mapping` handler.
- Generic runtime registration of the existing `physical-model` materializer.
- Entity→table, field→column, key→physical-key and relationship→physical-relationship mappings.
- Explicit mapping gaps for absent names, missing/ambiguous physical objects and missing physical relationships.

## Evidence policy

Only explicit persistence identifiers are used. JPA default naming, name-similarity matching, hidden fallback and legacy conceptual-model ingestion are unsupported.
