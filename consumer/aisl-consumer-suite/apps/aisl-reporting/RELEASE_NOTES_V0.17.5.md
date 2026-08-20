# Release notes — aisl-reporting 0.17.5

## Target-local continuation for workspace interaction attribute journeys

`workspace-interaction/v1` no longer truncates every representative attribute journey at the target HTTP request field.

For each already-selected bounded cross-boundary journey, Reporting now asks the existing KLC attribute-path resolver for a bounded continuation starting from the exact target boundary value node and restricted to the target repository.

The continuation is deliberately represented separately from the cross-boundary path:

- it does not change interaction matching;
- it does not promote confidence;
- it does not infer a business terminal or source of truth;
- partial continuations stay partial;
- branch points and exact gaps are preserved;
- up to two representative target-local paths are retained.

Selection prefers an observed natural terminal (`no_observed_outgoing_value_flow`) over a path merely stopped by a traversal budget, then stronger confidence and deeper evidence.

## Real workspace effect

On the four-repository System Interactions acceptance workspace:

- selected journeys remain bounded to 5;
- target-local continuation is now present for all 5 selected cards;
- phone flag code/endDate continue through target controller/orchestration/business-service fields;
- userinfo `sberProfileId` and `scope` continue through target service/context-building flows;
- report evidence index grows from 4 to 33 entries using already-published KLC provenance.

No Core or KLC code was changed.
