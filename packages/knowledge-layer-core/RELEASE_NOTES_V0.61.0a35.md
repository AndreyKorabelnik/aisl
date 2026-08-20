# knowledge-layer-core 0.61.0a35

Date: 2026-08-16

Introduces the KLC-owned Concept Detector Registry for Repository Inventory without changing detector semantics.

## Changes

- Added `knowledge_layer_core.concept_detector_registry` as the single owner of the six current concept detector definitions.
- Moved concept ids, claim boundaries, relevant official evidence kinds, detector dispatch and detector version ownership out of `repository_inventory_builder.py`.
- Repository Inventory builder now consumes the registry; it no longer embeds a second concept-definition/dispatch map.
- Generic discovery/novelty remains independent from concept classification.
- Core observed evidence ownership and Runner planning are unchanged in this release.

## Acceptance

- Registry targeted tests: 18/18 PASS across registry + Repository Inventory affected contracts.
- Full KLC regression: 256 PASS / 8 SKIPPED.
- Old canonical detector path vs registry parity probe: byte-identical classification + concept-status payload (`SHA-256 f702b051c58970b23d7a03103fbeeb362b838e5c9dd18d9fcdffba6518b79c91`).
- Fresh real gateway + datamart `--force-rebuild` publication: PASS; 12/12 concept status rows exact against Block C acceptance and all v3 acceptance counts exact.
