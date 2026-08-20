# Test status — FDP AT900 — aisl-reporting 0.13.2

## Automated tests

- Full aisl-reporting suite: `53 passed, 15 skipped`.
- FDP exact-case budget/ranking tests: `4 passed`.
- Optional real-UCP FDP contract: skipped because its external fixture was not configured.
- `compileall`: passed.
- Source manifest verification: passed.
- ZIP integrity verification: passed.

## Real AT900 validation

Input:

- code-analyzer-core `0.43.16/0.43.17` FDP facts;
- knowledge-layer-core `0.53.4` exact FDP case semantics;
- AT900 `client-profile` Knowledge Layer.

Result:

- deterministic report preparation: completed;
- compact dataset size: `423130` bytes;
- configured maximum: `500000` bytes;
- full canonical path count: `757`;
- selected report paths: `120`;
- omitted report paths: `637`, declared explicitly;
- full exact mechanical case count: `945`;
- selected exact cases: `160`;
- omitted exact cases: `785`, declared explicitly;
- confirmed exact cases: `11`;
- confirmed exact cases retained: `11`;
- evidence references: `141`.

Confirmed MNP evidence remains isolated to physical field `OPERATORID` and its exact source/access path pair. Confirmed `DEVICE_LINK` cases remain separate for `CLIENT_ID`, `DEVICE_ID`, and `UCP_ID`.

No LLM renderer was invoked during this validation. The deterministic dataset, renderer prompt, renderer messages, and run manifest were produced successfully.
