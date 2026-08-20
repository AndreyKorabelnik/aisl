# Repository Inventory — Concept Layer Removal / Core Discovery Decoupling

Date: 2026-08-17
Status: COMPLETE

## Architectural change
Repository Inventory is now a Core/evidence-level structural product. The six KLC semantic labels previously materialized inside Repository Inventory were removed together with the runtime Concept Detector Registry.

Removed from active Repository Inventory runtime:
- concept detector registry and detector classifications;
- repository concept status/classification tables;
- concept reports/summaries/detected-concept outputs;
- concept-evaluation gaps/diagnostics;
- concept filters/facets/endpoints in Prepared Runtime / Knowledge API / Portfolio;
- concept-specific SourceOccurrence links.

## Discovery correction
The previous repository-local `generic_novelty_score` was proven to be a salience measure, not a novelty proof. It has been renamed to `structural_salience_score`.

Repository Inventory no longer emits `structural_novelty` from a local threshold. Discovery kinds are now restricted to:
- `none`;
- `unknown_primitive` only when explicit Core analyzer-frontier evidence marks the structural family outside the supported frontier.

True novelty is downstream cross-repository mining over structural fingerprints (Benchmark Miner / Portfolio consumer), not a repository-local KLC inference.

## Preserved
- Core evidence and source provenance;
- structural families/members/fingerprints/metrics;
- SourceOccurrence and object-occurrence linkage;
- coverage, unresolved and diagnostics;
- preflight applicability / Runner selective execution;
- KLC knowledge materializers unrelated to Repository Inventory concepts.

Core and Runner source trees are unchanged.
