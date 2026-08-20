# AISL Storage Join Semantics — Test Status

Date: 2026-08-19

Targeted tests only; full regression was not run and is not claimed PASS.

- KLC materialization/contracts/cross-artifact/attribute-extension targeted group: 24/24 PASS.
- Prepared logical-storage query tests: 2/2 PASS.
- Knowledge API declared-data-model tests: 9/9 PASS.
- Knowledge Integration profile/binding tests: 20/20 PASS.
- Runner planning + Knowledge Control Plane targeted group: 55/55 PASS.
- aisl-client + aisl-cli targeted group: 20/20 PASS.
- Changed Python packages compile/import: PASS.
- Built-wheel import smoke: PASS.

Total non-overlapping targeted count recorded above: 130/130 PASS.

Not run:

- complete Core regression;
- complete Runner regression;
- complete KLC regression;
- complete Knowledge API regression;
- new real UCP production/import/query with logical-storage mapping v2.
