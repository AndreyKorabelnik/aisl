# code-analyzer-core 0.40.4

Iteration 28.2C preserves complete deterministic gap diagnostics across the prepared-artifact boundary.

- every projected `storage_lineage_gap` and `data_model_lineage_gap` now carries `source_gap_payload`;
- the nested payload preserves the original fact type, fact name and sanitized complete properties object;
- stable generic gap fields remain available for grouping and compact list queries;
- full diagnostics are written to the `code_conceptual_model/evidence_gaps.jsonl` detail section;
- no repository-, framework-, package-, class- or field-specific condition was introduced.

AT900 validation preserved all 7,391 missing facts and enriched all 7,391 with source-gap payloads.
