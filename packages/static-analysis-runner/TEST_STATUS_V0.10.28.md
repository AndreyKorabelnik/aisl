# Test status — static-analysis-runner 0.10.28

Date: 2026-08-17

- focused knowledge planning + execution-planning suite: **49/49 PASS**.
- real UCP `build-data-model-v1`: **PASS** through KCP → Runner → Core → KLC → Knowledge API publication.
- minimal Java/no-storage case: **PASS**; Core `model-storage-evidence` reports `coverage_status=not_applicable`, while the requested declared data model remains successful and no storage fact is fabricated.
- full Runner package regression: **not run** for this focused increment.
