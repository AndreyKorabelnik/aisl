# Test status — iteration 45

## Focused tests

- direct value-flow and resolver acceptance: 16 passed;
- query/evidence/suite/offline contract tests: 23 passed;
- full system interaction graph file: 10 passed;
- total completed focused tests: 49 passed, 0 failed.

The tests cover:

- confirmed request and reverse-response transport;
- probable candidate transport;
- evidence packet contents;
- loopback authority as non-binding evidence;
- `probable_complete` resolver status;
- strict confirmed-only traversal;
- unchanged interaction topology semantics.

A combined long process was not used as the source of truth because of the known accumulating
DuckDB process stall. Each completed file was run in a fresh process. Full regression was not
requested for this narrow iteration.


## Real-application benchmark

- probable matched interactions: 8;
- candidate HTTP transport edges: 226;
- confidence promotions: 0;
- explicitly conflicting authority test: passed.
