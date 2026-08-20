# AISL Reachability GC — Test Status

Date: 2026-08-16

Authoritative completed runs:

- Knowledge API: **118/118 PASS** (`49 + 35 + 34`).
- Post-final service refinement targeted API/contract: **22/22 PASS**.
- Prepared Knowledge Runtime: **10/10 PASS**.
- Knowledge Integration: **19/19 PASS**.
- Knowledge Reporting: **100 PASS / 2 SKIPPED**.
- AISL Contract 0.3.0b8: **47/47 PASS**.
- KLC: **252 PASS / 8 SKIPPED** (`76+89+87 PASS`, `7+1 SKIPPED`).
- KCP: **95/95 PASS**.
- Deterministic GC E2E acceptance: **PASS**.

A monolithic KLC run hit the external execution timeout and was not counted. One malformed API pytest command referenced a non-existent file and ran zero tests; it was not counted.
