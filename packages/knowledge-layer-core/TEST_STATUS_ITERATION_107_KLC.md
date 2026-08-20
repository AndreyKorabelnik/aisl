# Iteration 107 KLC test status

## Completed

- focused physical-model materialization and query tests: 8 passed;
- affected KLC query/contract regression: 25 passed;
- compileall: passed;
- real PDM query smoke through Knowledge API: passed.

The real `PDM_B2C_restored` artifact exposed 522 tables, 11,940 columns, 498 keys, 370 resolved relationships and 0 gaps.

## Not run

The complete KLC suite and full platform regression were not run. The change is limited to read-only physical-model queries and capability advertisement; builders, SQL materialization, data-model materialization and topology were not changed.
