# Test results — 0.9.32

## Automated tests

- `python -m pytest -q`: **84 passed**.
- focused portfolio contracts/runner tests: **8 passed**.
- `compileall`: passed.

## Real HTTP Islands E2E

- repositories: **4/4 completed**;
- HTTP boundaries: **49**;
- system interactions: **3**;
- boundary interactions: **8**;
- strict islands: **4**;
- extended islands: **1**;
- matched/probable outbound operations: **8**;
- unresolved outbound operations: **14**;
- temporary clone removed after each repository: passed;
- temporary analysis output removed after each repository: passed;
- persistent repository results contain no temporary work paths: passed;
- final schema validation: passed.

## Dependencies used for E2E

- code-analyzer-core 0.43.18;
- knowledge-layer-core 0.53.5;
- DuckDB 1.5.5.
