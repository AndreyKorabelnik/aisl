# System Interactions real validation — aisl-reporting 0.17.5

Upstream state:
- Core 0.44.16
- KLC 0.59.29
- Reporting input: fixed four-repository workspace artifact

Selected detailed journeys: 5.

Observed target-local continuations:

1. `phone.flags.flagType.code` -> target controller/orchestration/business service, 5 confirmed steps; terminal gap `no_observed_outgoing_value_flow`.
2. userinfo `sberProfileId` -> target service/context/model flow, bounded continuation with confirmed steps and explicit traversal gaps/branches.
3. phone-flags `sberProfileId` -> target search-client preparation including external client id, confirmed target-local steps.
4. userinfo `scope` -> target context builder / scope building, confirmed target-local steps.
5. `phone.flags.endDate` -> target controller/orchestration/business service, 5 confirmed steps; terminal gap `no_observed_outgoing_value_flow`.

Report evidence index increased from 4 entries in 0.17.4 validation to 33 entries in 0.17.5 validation because existing target-side KLC provenance is now included.

Known gaps are preserved:
- target-local phone flag paths currently stop before the manual-Gold `Long.parseLong -> ContactFlagType.code` mapping because the current value-flow graph does not connect that downstream mapper segment;
- update/create currently has rich field contracts but no representative transport edge/journey in the cross-repository value-flow artifact;
- KLC confidence/path-case policy is unchanged.
