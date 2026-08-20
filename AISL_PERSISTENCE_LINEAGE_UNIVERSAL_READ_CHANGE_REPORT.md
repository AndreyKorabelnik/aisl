# AISL persistence-lineage universal read — change report

Date: 2026-08-15
Status: PERSISTENCE_LINEAGE_UNIVERSAL_READ_BLOCK_COMPLETE

## Scope decision

The requested continuation first investigated a real positive `logical-physical-mapping` / `maps_to` acceptance case.

Observed result: the available real Java repositories do not contain JPA/Jakarta persistence annotations required by the current `java-persistence-mapping-evidence/v1` contract. The existing mapping materializer intentionally accepts only explicit persistence identifiers and does not infer default names or name similarity.

Therefore no positive `maps_to` relation was synthesized. That P1 item remains an explicit real-input evidence gap.

A separate consumer-driven need was proven on real AT900 code: the typed `persistence-lineage/v1` product already contains confirmed source-field → storage-field paths, but AISL universal exact read did not project that product. This block implements that read boundary without adding a producer or changing Core evidence semantics.

## Architecture

Unchanged producer path:

```text
Formalized source
→ Core persistence-lineage evidence
→ Runner
→ KLC persistence-lineage typed product
→ knowledge_execution_result/v2
→ Knowledge API publication
════════ publication boundary ════════
→ Prepared Runtime universal exact read
→ Knowledge API / external consumer
```

No Core analyzer, Runner execution path, mapping producer, vector index, fuzzy matcher, or semantic inference engine was added.

## Changed modules

### knowledge-layer-core 0.61.0a30

Observed bug found during real acceptance: generic `subject_knowledge_builder` local-ID selection could select a nested related `storage_access_id` before a source lineage record's own `source_to_storage_lineage_id`. The typed product therefore did not always expose stable product-owned item identity.

Fix:
- persistence-lineage product owner now selects the canonical identity field for each of its six artifact families;
- a missing required owner ID fails materialization explicitly;
- no fallback to nested/related IDs;
- no compatibility alias or dual identity.

Canonical item identity fields:
- `source_to_storage_lineage.json` → `source_to_storage_lineage_id`
- `storage_to_access_lineage.json` → `storage_to_access_lineage_id`
- `persistent_writes.json` → `persistent_write_id`
- `storage_accesses.json` → `storage_access_id`
- `storage_lineage_gaps.json` → `storage_lineage_gap_id`
- `stored_field_to_response_field_mappings.json` → `stored_field_to_response_field_mapping_id`

### prepared-knowledge-runtime 0.1.0.post7

Extends the existing AISL universal exact-item dispatcher for the typed `persistence-lineage/v1` product.

Supported exact item kinds:
- `source_to_storage_lineage`
- `storage_to_access_lineage`
- `persistent_write`
- `storage_access`
- `storage_lineage_gap`
- `stored_field_to_response_field_mapping`

The projection:
- reads only the published typed product record;
- keeps the raw typed payload;
- projects direct observed source locations into AISL evidence/source fragments;
- exposes unresolved/ambiguous/candidate states as issues;
- exposes `storage_lineage_gap` as `missing_information` with missing links and source-inspection requests;
- leaves item-level coverage `not_available` when the typed owner has not published item-level coverage;
- does **not** create a `maps_to` or other cross-product correspondence.

### knowledge-api 0.30.10

No new execution/materialization route. Existing universal knowledge-item endpoint now exposes Prepared Runtime 0.1.0.post7. Canonical dependencies aligned to:
- `knowledge-integration==0.1.8`
- `prepared-knowledge-runtime==0.1.0.post7`

Stored OpenAPI regenerated from the canonical application builder after the version change.

## Explicit non-changes

- evidence-common unchanged 0.23.2
- code-analyzer-core unchanged 0.44.23a5
- static-analysis-runner unchanged 0.10.25
- knowledge-integration source unchanged 0.1.8
- knowledge-reporting unchanged 0.18.0
- knowledge-control-plane unchanged 1.2.0a22
- aisl-contract unchanged 0.3.0b3

## Semantics / evidence discipline

A persistence lineage means observed technical data movement/storage evidence. It is not silently reclassified as logical↔physical identity.

For example:

```text
SyncPushDeviceRequest.clientId
→ DEVICE_LINK.CLIENT_ID
```

is published/read as confirmed persistence lineage (`source_to_storage_lineage`), **not** as `maps_to` between a code-declared model item and a physical-model item.

Cross-product correspondences remain `unsupported` for this item family until a separate consumer need and product-owned relation justify such a projection.
