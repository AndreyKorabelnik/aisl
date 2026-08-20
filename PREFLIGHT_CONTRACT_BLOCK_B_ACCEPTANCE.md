# Preflight Contract Block B — Acceptance

Date: 2026-08-16
Status: PASS

## Goal
Make the current Repository Inventory bounded-production policy executable end-to-end without creating a second planner, parser path, or Concept Discovery subsystem.

## Architectural result

Core owns deterministic preflight planning metadata for typed evidence contracts.
KLC Repository Inventory owns the bounded materialization input policy.
Runner preserves that owner-provided policy when composing `knowledge_catalog/v2` and remains the sole execution planner.
KCP consumes the pinned owner catalogs; it does not reconstruct policy.

No concept inference is used yet to select/skip analyzers.

## Core planning classes

- P0 / always-on: `repository-structure-evidence/v1`
- P1 / bounded preflight:
  - `data-model-candidate-evidence/v1`
  - `interaction-boundary-evidence/v1`
  - `structured-file-shape-evidence/v1`
- full-analysis: remaining 9 current evidence contracts

Every contract carries safety metadata. In particular, concept inference may not hard-skip an analyzer; hard skip requires observed non-applicability and an explicit request must execute or report an observed blocking precondition.

## Real bug found and fixed

Observed before the fix: `build-repository-inventory-v1` on a fresh repository scheduled 12 Core analyzers, including deep `existing_only` inputs.

Root cause: KLC materialization contracts correctly carried `production_policy`, but Runner `_evidence_source()` dropped that field for Core-owned evidence while composing the user-facing Knowledge Catalog. Resolution then defaulted missing policy to `produce_if_missing`.

Fix: preserve owner-provided `production_policy` for Core evidence. No new planner or registry was introduced.

## Real acceptance — gateway

- system: `preflight-gateway-fixed`
- job: `job-755293c384f7468da7b33a76feb57f62`
- revision: `rev-275eb494d30c835652f70aff`
- status: succeeded
- planned Core analyzers: exactly 4
  - data-model-candidate-analyzer
  - interaction-boundary-analyzer
  - repository-structure-analyzer
  - structured-file-shape-analyzer
- deep existing-only analyzers executed: 0
- Repository Inventory materialization: succeeded
- publication: succeeded
- observed one-shot wall time: ~25 seconds

Published Repository Inventory includes:
- `structural_member_count = 12`
- `structured_shape_family_count = 9`
- deep concepts without relevant evidence remain `not_evaluated`, not guessed.

## Real acceptance — datamart_profile_fl

- system: `preflight-datamart-fixed`
- job: `job-f0f0b911031b4b9cbf6dba369972a838`
- revision: `rev-54792c6179de4c482839796a`
- status: succeeded
- planned Core analyzers: exactly 4 P0/P1 analyzers
- `sql-analysis-analyzer`: NOT executed (`sql-analysis` remains `existing_only`)
- all full-analysis analyzers: NOT executed
- Repository Inventory materialization: succeeded
- publication: succeeded
- observed one-shot wall time: ~18 seconds

Published Repository Inventory includes:
- `structural_member_count = 156`
- `structured_shape_family_count = 14`

## Explicit boundary / remaining gap

The current Runner does not yet use the new Core-owned `preflight_planning.applicability` metadata to skip irrelevant P1 producers. Therefore the SQL-heavy datamart still runs cheap Java-oriented candidate/boundary probes. This is visible and intentionally deferred to the later preflight-aware planning block.

The current weak `data_model` signal on that SQL-heavy repository is therefore not evidence that the concept is confirmed. Repository Inventory vNext must keep generic structural discovery, concept inference, and coverage/discovery taxonomy separate.

## Acceptance verdict

PASS for Block B:
- official owner policies reach the execution plan;
- default Repository Inventory is bounded;
- structured-file-shape is a real P1 input;
- deep optional evidence is not silently produced;
- no second observed producer/planner/parser was added.
