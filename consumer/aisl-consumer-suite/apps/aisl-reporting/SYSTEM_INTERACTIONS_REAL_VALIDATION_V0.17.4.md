# System Interactions real validation — aisl-reporting 0.17.4

Real workspace:

- `sbpr-ucp-intergation`
- `gateway-sberid-userinfo-by-ucpid`
- `gw-sberid-update-phone-flags`
- `gw-sberprofile-create-update-extprofile`

Upstream validation state:

- Core 0.44.16 evidence from completed real workspace run;
- KLC 0.59.29 typed interaction context composition checkpoint;
- 3 system boundary interactions;
- 8 execution contexts;
- 46 interaction field contracts;
- 9 cross-repository transport edges.

The current runtime does not materialize `interaction-coverage` for this profile.

## Before 0.17.4

- repository role items: 0
- Mermaid repository nodes: 0
- reported inbound boundaries: 0
- reported outbound boundaries: 0
- reported matched outbound: 0
- selected detailed attribute journeys: 9

The zero counts were a reporting-composition artifact, not absence of KLC boundary evidence.

## After 0.17.4

- repository role items: 4
- Mermaid repository nodes: 4
- observed inbound boundaries: 27
- observed outbound boundaries: 17
- matched outbound interactions: 3
- confirmed outbound interactions: 0
- probable outbound interactions: 3
- ambiguous outbound diagnostics: 0
- unresolved outbound diagnostics: 14
- execution contexts: 8
- field contracts: 46
- transport edges: 9
- selected detailed attribute journeys: 5
- `published_interaction_coverage_available=false`

`count_basis` explicitly states that boundary/match counts come from canonical technical records and that analysis/coverage statuses are used only when the optional interaction-coverage mart is published.

## Known limitations

- KLC confidence/path case policy was intentionally not changed in this reporting release.
- One of six Manual Gold update/create source contexts is still an upstream evidence gap; the report keeps the five observed contexts.
- The report still needs final LLM rendering/richness comparison against Manual Gold Report and old `llm-prompts v0.31.0`; this release fixes the deterministic dataset before that comparison.
