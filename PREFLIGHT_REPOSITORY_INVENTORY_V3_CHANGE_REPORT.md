# Repository Inventory v3 — Block C Change Report

Date: 2026-08-16

## Changed runtime contracts

### Knowledge Layer Core 0.61.0a34
- `repository-inventory/v3` schema and builder.
- Explicit evaluation phase.
- Separate completeness/coverage-gap, discovery and concept-classification axes.
- First-class coverage-gap rows.
- Structural novelty remains distinct from `unclassified_concept_candidate`.
- Existing six concept detector semantics preserved.

### Prepared Knowledge Runtime 0.1.0.post10
- Repository Inventory v3 query support.
- Discovery and coverage-gap reads separated.
- No fallback to the removed `/unclassified` semantics.

### Knowledge API 0.35.0
- Repository Inventory v3 public read contract.
- `/discovery` and `/coverage-gaps` endpoints.
- Portfolio projection includes evaluation phase and v3 counts.
- OpenAPI regenerated for the current public contract.

### Knowledge Control Plane 1.2.0a25
- Pinned owner catalogs regenerated from Core 0.44.23a6 / KLC 0.61.0a34 / Runner 0.10.26.
- Pinned knowledge/materialization catalogs publish `repository-inventory/v3` and its current capabilities.

## Explicitly unchanged

- Core observed evidence semantics are unchanged by Block C.
- Runner execution semantics are unchanged by Block C.
- No detector registry yet; that is the next block.
- Runner does not yet use applicability metadata to skip producers.
- FI-002 and other parked scope remain parked.
