# Test Status — aisl-reporting 0.1.0

Date: 2026-08-17

- isolated module suite: 93/93 PASS;
- compileall/import: PASS;
- actual Knowledge API integration smoke: PASS — a revision was published through the current Knowledge API contract and `data-model-report/v1` built `report_dataset/v1` from that pinned revision;
- no Core/Runner/KLC/KCP runtime dependency is declared;
- full framework regression was not run because Reporting is now outside the framework.
