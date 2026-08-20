# knowledge-layer-core 0.23.0

## Foreign-data-persistence query contracts

- Added `ForeignDataPersistenceQueryService`.
- Exposes complete facts-only FDP path catalogs and exact evidence.
- Preserves source→storage and storage→access segments independently.
- Groups segments mechanically only by exact storage-object identity.
- Confirms end-to-end same-data only when both segments contain exact overlapping storage fields.
- Never assigns business FDP or risk decisions.
- Normalizes evidence and path-like fact properties for portable datasets.

## Validation

The real UCP full-suite fixture contains four storage→access fragments, zero source→storage fragments, three mechanical storage groups and zero confirmed end-to-end same-data cases. This fixture is intentionally treated as a negative guardrail, not as a positive FDP finding.
