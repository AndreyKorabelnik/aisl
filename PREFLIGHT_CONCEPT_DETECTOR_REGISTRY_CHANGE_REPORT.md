# Preflight Concept Detector Registry — Block D Change Report

Date: 2026-08-16
Status: COMPLETE

## Architecture

Block D creates one KLC-owned Concept Detector Registry for the six existing Repository Inventory concepts. It is an ownership/refactoring step, not a new analyzer or new inference layer.

Before Block D, `repository_inventory_builder.py` owned three parallel concept-definition fragments: the claim-boundary map, relevant-evidence map and detector dispatch logic. After Block D, these live in `knowledge_layer_core.concept_detector_registry` as one ordered registry. The Repository Inventory builder consumes that registry.

Preserved invariants:
- Core remains sole owner of observed evidence;
- Repository Inventory remains one KLC product and one materialization path;
- discovery/novelty remains concept-agnostic;
- six concept ids and semantics are unchanged;
- no compatibility adapter, dual-read/write or second planner was introduced;
- Runner selection is intentionally unchanged in Block D.

## Changed modules

- knowledge-layer-core: `0.61.0a34` → `0.61.0a35`; owns the new registry.
- knowledge-control-plane: `1.2.0a25` → `1.2.0a26`; pinned runtime catalogs regenerated from the canonical KLC/Runner builders. Core evidence catalog remains byte-identical.

## Next

Block E may now connect Core-owned `preflight_planning.applicability` metadata to the existing Runner planning/selection path. Hard skip must require observed non-applicability and must not be derived from uncertain concept inference.
