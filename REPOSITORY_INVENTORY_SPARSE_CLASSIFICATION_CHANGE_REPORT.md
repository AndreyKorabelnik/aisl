# Repository Inventory — Sparse Concept Classification Change Report

Date: 2026-08-16  
Status: **COMPLETE**

## Change

Repository Inventory no longer persists the dense Cartesian product `structural families × all registered concepts` at family-classification level.

KLC now evaluates/persists a family-level concept classification only when the family's official `source_artifact_kind` is covered by the detector registry entry `relevant_evidence_kinds`.

Repository-level `concept_status` remains dense for every registered concept. Relevant evaluated-but-not-classified rows are preserved. Absence of a family-level classification row means **detector not applicable to that evidence kind**, not `not_detected`.

## Architecture

- Core observed evidence is unchanged.
- No repository/source rescan was added to KLC.
- The six detector ids and detector inference semantics are unchanged.
- Concept Detector Registry remains the single KLC owner of detector relevance.
- Repository Inventory remains one materialization/product.
- No compatibility adapter, dual write/read, fallback or second source of truth was introduced.

## Modules

- knowledge-layer-core `0.61.0a35 → 0.61.0a36`.
- knowledge-control-plane `1.2.0a27 → 1.2.0a28` only to repin the KLC/Runner runtime contract bundle.
- Core `0.44.23a7`, Runner `0.10.27`, Prepared Runtime `0.1.0.post10`, Knowledge API `0.35.0` unchanged.

## Real effect

Fresh force-rebuild Runner → Core → KLC runs on the current selective-execution baseline:

- gateway: `126 → 2` family classification rows (`−98.413%`); compact Repository Inventory JSON `208,763 → 109,423 bytes` (`−47.585%`).
- datamart: `168 → 1` family classification rows (`−99.405%`); compact JSON `529,761 → 358,449 bytes` (`−32.338%`).

All checked semantic/structural sections are identical to a dense counterfactual generated from the same fresh evidence set. Six repository-level concept statuses remain present in both cases.
