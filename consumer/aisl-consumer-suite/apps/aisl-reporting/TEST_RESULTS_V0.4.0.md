# aisl-reporting 0.4.0 — Test Results

Date: 2026-08-18

- Full aisl-reporting suite: **98/98 PASS**
- Targeted new-profile/common-boundary suite: **19/19 PASS**
- Compile/import: PASS
- Real UCP `declared-data-model-report/v1` prepare/build: PASS
- Real UCP dataset: 1,116,969 bytes; compact catalog 1326/1326 complete; detailed contexts 20
- Real UCP `Individual`: 52 fields / 41 relationships; storage context `available`
- `Individual.birthPlace`: `ambiguous`, two confirmed candidate key expressions, physical mapping `not_observed`, `physical_join_confirmed=false`
- `Individual.birthCountry`: no relationship mapping observed; three reference-value derivations retained; physical mapping `not_observed`
- Existing `data-model-report/v1` on the same declared-only revision: expected strict refusal (requires `common.effective-data-model`) — PASS
- Platform ReportRun through reporting HTTP service: completed; dataset/report validation conforms with zero warnings
- Platform Chat transport/tool-loop on the same revision: PASS (fixture provider; not counted as independent LLM behavioral validation)

No full framework regression was run because framework code did not change.
