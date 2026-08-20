# Release notes — aisl-reporting 0.17.4

## Workspace interaction report richness/composition

This release fixes two generic reporting regressions found by comparing the real four-repository workspace against the frozen Manual Gold report and the older `llm-prompts v0.31.0` richness contract.

### 1. Repository roles, map nodes, and technical counts no longer depend on the optional interaction-coverage mart

`workspace-interaction/v1` now derives observable per-repository interaction summaries from canonical KLC records that are already present in the reporting artifact:

- `repository_interaction_boundary`;
- `system_boundary_interaction`;
- interaction match diagnostics.

This is not a silent fallback for analysis coverage. Boundary/match counts use an explicit evidence basis, while `analysis_status`, `coverage_status`, and `matching_coverage_status` are populated only when the published interaction-coverage mart exists.

The report can therefore still show:

- repository technical role candidates;
- all workspace nodes in the Mermaid map;
- observed inbound/outbound counts;
- matched/confirmed/probable/ambiguous/unresolved disposition counts;

without pretending that unavailable analysis-coverage knowledge is known.

### 2. Representative attribute journeys are bounded to the report contract

Journey budgets are now:

- executive: 2;
- standard: 4;
- detailed: 5.

The renderer guidance now targets about 20–30% of the main text and never more than one third for attribute journeys. This aligns the implementation with:

- the existing report dataset schema (`required_card_count <= 5`);
- the builder's own selection policy;
- the older rich workspace interaction report contract used as a richness benchmark.

## Architecture

No Core or KLC evidence semantics were changed in this release. The fix is intentionally limited to the reporting composition/presentation layer.
