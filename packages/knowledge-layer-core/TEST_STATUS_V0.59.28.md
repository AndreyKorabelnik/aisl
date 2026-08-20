# Test status — knowledge-layer-core 0.59.28

- KLC persistence/FDP targeted tests: **1 passed, 1 skipped** (external UCP fixture unavailable in this runtime).
- Knowledge Reporting FDP budget/profile regression against KLC 0.59.28 source: **4 passed**.
- Real AT900 read-side check on Core 0.44.16 / KLC persistence artifact: **PASS**.
  - 781 canonical FDP paths = 529 source→storage + 252 storage→access.
  - 969 mechanical cases.
  - 8 confirmed exact same-data cases preserved.
  - 8 confirmed external-ingress source→storage paths preserved.
- `compileall`: PASS.
- source manifest and ZIP integrity: PASS.
