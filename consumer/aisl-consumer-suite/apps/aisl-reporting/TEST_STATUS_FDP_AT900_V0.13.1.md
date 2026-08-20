# Test status — FDP AT900 — aisl-reporting 0.13.1

## Automated tests

- Full aisl-reporting suite: `52 passed, 15 skipped`.
- FDP budget/ranking tests: `3 passed`.
- Optional real-UCP FDP contract: skipped because its external fixture was not configured.
- `compileall`: passed.
- Source manifest verification: passed.
- ZIP integrity verification: passed.

## Real AT900 validation

Input:

- code-analyzer-core `0.43.13` FDP suite output;
- knowledge-layer-core `0.53.3` query semantics;
- AT900 `client-profile` Knowledge Layer.

Result:

- deterministic dataset build: completed in about 1.1 seconds;
- dataset size: `311324` bytes;
- configured maximum: `500000` bytes;
- full canonical path count: `728`;
- selected report paths: `120`;
- omitted report paths: `608`, declared explicitly;
- same-data confirmed mechanical cases: `6`;
- executive assessment: `end_to_end_same_data_observed`;
- evidence references in prepared dataset: `120`.

The `DEVICE_LINK` case was retained without path truncation and contains exact overlap:

- `CLIENT_ID`;
- `DEVICE_ID`;
- `UCP_ID`.

No LLM renderer was invoked during this validation. The deterministic dataset, renderer prompt, renderer messages, manifest, and validation summary were produced successfully.
