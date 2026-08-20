# aisl-reporting 0.13.1

## FDP report budget and connected-case prioritization

- Added deterministic path selection for large Foreign Data Persistence datasets.
- Confirmed end-to-end same-data cases are selected before confirmed standalone paths, connected partial cases, and unresolved background paths.
- Full counts, maturity summaries, missing-link summaries, and governance guardrails still use the complete canonical catalog.
- The renderer receives a bounded excerpt of at most 120 paths and up to 80 detailed gap items; omitted counts are explicit.
- Mechanical cases preserve total and selected path counts and declare whether their path excerpt was truncated.
- The renderer prompt now requires confirmed `source → storage → access` cases and exact field overlap to appear before partial fragments.
- No raw Knowledge Layer facts, business FDP verdicts, or risk decisions are changed.
