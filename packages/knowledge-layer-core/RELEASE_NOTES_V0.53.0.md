# knowledge-layer-core 0.53.0

Adds deterministic materialization of the existing `physical-model/v1` artifact produced by code-analyzer-core.

The new `build_physical_model_knowledge_layer()` builder validates the source manifest, fact order, IDs, counts, file sizes, SHA-256 hashes, content fingerprint, source metadata and coverage. It materializes typed tables for physical tables, columns, keys, relationships and non-blocking gaps into a standard `knowledge-layer.duckdb`.

PDM does not assign source/target roles. SQL-observed `read` and `write` usage remains authoritative for those roles.
