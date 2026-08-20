# knowledge-layer-core 0.59.1 — real data-model transactions

- Wraps `code-declared-data-model` ingestion, derived-field expansion, validation metadata, and build finalization in one explicit DuckDB transaction.
- Wraps `effective-data-model` composition, gap copying, logical rows, unmapped physical objects, coverage, and build finalization in one explicit DuckDB transaction.
- Removes per-row autocommit overhead observed on the real `client-profile` repository and the 522-table PDM.
- Keeps typed contracts, model semantics, counts, diagnostics, validation, and atomic directory publication unchanged.
- Rolls back active transactions explicitly on failure; no fallback or dual-write was added.
