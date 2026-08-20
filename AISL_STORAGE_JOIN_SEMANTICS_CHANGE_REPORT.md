# AISL Storage Join Semantics — Change Report

Date: 2026-08-19

## Goal

Make code/XML-derived storage relationships usable by AI consumers even when a system has no PDM, without weakening evidence discipline or asserting physical SQL/PDM joins.

## Architecture

No new analyzer, materializer, product, publication path or API-side inference was introduced.

Existing ownership is preserved:

Sources → Core → Runner → KLC → Prepared Knowledge/AISL → Knowledge API → Consumers

- Core remains owner of observed evidence.
- `logical-storage-mapping` remains KLC owner of logical↔storage useful knowledge.
- Existing exact structural expression correspondence logic is shared rather than duplicated.
- Knowledge API only exposes published KLC knowledge.
- `aisl-client` owns compact consumer projection; CLI delegates to SDK.

## Changes

### KLC

- `logical-storage-model-mapping` schema bumped to `v2`.
- Added `logical_storage_join_semantic` mart.
- Added capability `common.logical-storage-join-semantics`.
- Join semantics are derived per declared relationship occurrence, not per field, so one field can retain multiple relationships.
- Exact source-reference ↔ target-identity structural correspondence reuses the existing canonical expression matcher.
- Concrete subtype storage targets remain compatible with declared base/abstract targets through already-observed inheritance semantics.
- No name similarity, case folding, domain normalization, PDM or SQL inference was added.
- Exact structural correspondence is classified as `strongly_supported` derived knowledge with `join_readiness=executable_storage_join`; it is not promoted to an observed fact.
- Ambiguous candidates remain explicit.
- `physical_join_claimed=false` remains part of basis.

### Prepared Knowledge

- Logical storage object context upgraded to `logical-storage-object-context/v2`.
- Published join semantics are read as first-class rows.

### Knowledge API / Integration Profile

- `data_model_object_context` upgraded to `v2`.
- Each relationship exposes its own `storage_join` projection.
- Missing join semantics are explicit `unresolved/not_available`; no fallback is synthesized.
- Integration binding now expects `data_model_object_context/v2`.

### aisl-client / CLI

- Compact data-model projection moved from CLI into public `aisl-client` SDK.
- Default projection keeps `relationships[]` as an independent graph.
- One field may reference multiple relationship rows.
- Default relationship payload keeps consumer-relevant status, readiness, expressions, target key fields, match basis and evidence ids.
- Long derivations/provenance/physical details are emitted only with provenance/detail mode.
- Repeated `physical_join_confirmed=false` is not emitted in compact relationship payload.
- CLI remains a thin presentation layer over the SDK projector.

## Claim boundary

`executable_storage_join` means that the storage-level correspondence has sufficient published evidence for an agent to use the storage identity rule. It does not mean that a physical SQL JOIN or PDM correspondence was observed.
