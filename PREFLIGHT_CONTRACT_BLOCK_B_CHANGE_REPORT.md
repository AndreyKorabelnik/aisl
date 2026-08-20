# Preflight Contract Block B — Change Report

Date: 2026-08-16

## Changed modules

### code-analyzer-core 0.44.23a6
- Added Core-owned `preflight_planning` metadata to all 13 typed evidence contracts.
- Validates execution class, phase, discovery role, applicability, budget, and selection-safety invariants.
- No analyzer/parser semantics changed.

### knowledge-layer-core 0.61.0a33
- Promoted `structured-file-shape-evidence/v1` to `produce_if_missing` for Repository Inventory after real bounded-cost measurement.
- Repository Inventory report `evaluation_policy` now derives from the official `CURRENT_MATERIALIZATIONS` contract rather than a duplicate hardcoded policy list.
- No concept detector semantics changed.

### static-analysis-runner 0.10.26
- Projects Core-owned preflight planning metadata into `knowledge_input_inventory/v1` without using it yet for selection decisions.
- Preserves KLC owner-provided `production_policy` for Core evidence in `knowledge_catalog/v2`.
- Added regression proving default Repository Inventory schedules only required/`produce_if_missing` evidence and does not schedule deep `existing_only` producers.
- Updated stale test baselines to current catalog/registration counts; no compatibility path added.

### knowledge-control-plane 1.2.0a24
- Regenerated pinned Core/KLC/Runner runtime contract bundle from canonical owner builders.
- No planning semantics added to KCP.

## Not changed
- AISL Contract / persistence lifecycle
- Knowledge API
- Prepared Runtime
- Knowledge Integration
- Knowledge Reporting
- Benchmark Miner
- Concept Detector implementation
- Repository Inventory schema version (`v2` remains current in this block)

## Architecture preserved
- Core is the only owner of observed evidence/stage applicability metadata.
- KLC is the owner of Repository Inventory inference and materialization policy.
- Runner is the only execution planner.
- KCP orchestrates and consumes pinned official contracts.
