# aisl-reporting 0.17.7

## Workspace interaction negative controls and owner questions

This release closes two report-richness gaps without changing interaction matching semantics.

The workspace interaction dataset now exposes unmatched inbound operations separately from unmatched/ambiguous outbound diagnostics. Inbound evidence records that represent the same technical operation are grouped by repository/protocol/method/path; if any sibling evidence record is the target of a matched interaction, the operation is not reported as unmatched.

Owner questions are no longer limited to four generic templates. The dataset deterministically publishes up to 15 concrete questions grounded in observed probable routes, unresolved outbound operations, unmatched inbound operations, bilateral response-contract gaps and partial attribute journeys.

No Core or KLC behavior changed. No business semantic classification was moved into deterministic code.
