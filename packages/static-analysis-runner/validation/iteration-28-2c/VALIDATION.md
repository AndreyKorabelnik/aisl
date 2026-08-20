# Iteration 28.2C validation

This checkpoint preserves complete deterministic source-gap diagnostics across:

`Fact -> code_conceptual_model.evidence_gaps.jsonl -> knowledge-layer DuckDB -> public evidence detail tool`.

Real AT900 replay results:

- source evidence gaps: 7,391;
- gaps carrying `source_gap_payload`: 7,391;
- DuckDB `workspace_missing_fact` rows: 7,391;
- enriched DuckDB rows: 7,391;
- list queries remain compact;
- detail query and public evidence command return the same full payload.

The JSON file in this directory contains the machine-readable validation result. The test result
file records the module-specific regression result used for this checkpoint.
