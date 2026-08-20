# Repository Inventory v3 — Contract Design

Date: 2026-08-16
Status: implementation in progress
Base: Preflight Contract Block B canonical

## Purpose
Separate four concerns that were partially conflated in repository-inventory/v2:
1. snapshot evaluation phase;
2. completeness / coverage gaps;
3. generic structural discovery/novelty;
4. concept classification inference.

## Invariants
- one Repository Inventory product only;
- Core remains the only observed-evidence owner;
- generic discovery does not depend on concept vocabulary;
- six current concept detectors retain semantic parity in this block;
- current structural novelty is not renamed to `unclassified_concept_candidate`;
- FI-002 remains parked;
- no dual-read/dual-write compatibility path.

## Evaluation phase
- `preflight`: supplied evidence is limited to Repository Inventory required/produce_if_missing inputs;
- `post_analysis`: at least one Repository Inventory `existing_only` evidence artifact is supplied.
The phase is derived from KLC-owned materialization policy plus actual supplied evidence.

## Coverage axis
`repository_inventory_completeness` represents current completeness for repository landscape, supplied evidence and concept evaluation.
`repository_inventory_coverage_gap` represents visible technical gaps with provenance, discovery kind, relevance and diagnostics.

Coverage states include `complete`, `supported_with_gaps`, `partial`, `unsupported`, `not_evaluated`, `ignored_with_reason`.

## Discovery axis
Structural family `discovery_kind`:
- `known_concept` — explained by at least one current concept detector;
- `unknown_primitive` — observed structural family is outside the current analyzer frontier;
- `structural_novelty` — generic novelty candidate not explained by current detectors;
- `none` — no discovery candidate classification.

The stronger states `known_concept_new_representation`, `unknown_composition` and `unclassified_concept_candidate` are valid taxonomy targets but are not fabricated without stronger evidence. `unclassified_concept_candidate_count` must remain zero in this parity block.

## Concept axis
Existing concept classification/status remains inference with the same six concept ids, status/confidence semantics, basis and claim boundaries.
