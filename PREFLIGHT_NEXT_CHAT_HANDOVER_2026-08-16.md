# Handover — Preflight / Concept Discovery

Date: 2026-08-16
Current status: PREFLIGHT_CONTRACT_BLOCK_B_COMPLETE

## Restore first
Use the recovery/canonical produced for this block and verify SHA/manifests before changes.

## Completed
Block A — Preflight Evidence Audit:
- no runtime changes;
- confirmed existing Repository Inventory concept discovery and current Runner planner;
- identified P0/P1/full evidence classification and missing generic Java/SQL preflight projections.

Block B — Preflight Execution Contract:
- Core-owned planning metadata is official on all 13 evidence contracts;
- Repository Inventory default production is bounded;
- structured-file-shape is P1 `produce_if_missing`;
- Runner preserves KLC `production_policy` and no longer turns deep `existing_only` evidence into implicit production;
- real gateway/datamart acceptance published successfully.

## Important explicit gap
Applicability metadata is NOT yet used by Runner selection. SQL-heavy repositories can still execute cheap Java-oriented P1 probes. Do not hide this with concept inference or application-specific rules.

## Next agreed block
Repository Inventory vNext / v3 design and implementation:
- `evaluation_phase = preflight | post_analysis`;
- separate axes for coverage status, discovery kind, and concept classification/confidence;
- distinguish structural novelty from true `unclassified_concept_candidate`;
- retain explicit unknown/partial/unsupported diagnostics;
- do not add a second inventory product.

After vNext parity, migrate the six current concept detectors into a KLC-owned detector registry without semantic changes. Preflight-aware Runner selection comes after the inventory/detector contracts are stable.

## Parked / do not auto-resume
- FI-002 generic cross-artifact unknown-family correspondence
- vector/embedding retrieval
- portfolio topology
- universal graph
- agent memory/planning
- compatibility cleanup without a proven duplicate
