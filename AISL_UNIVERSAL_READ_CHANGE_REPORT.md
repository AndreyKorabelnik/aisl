# AISL Universal Read — Change Report

Date: 2026-08-15

## Goal

Provide the smallest universal AISL consumer read projection:

```text
KnowledgeItemRef
→ typed item
→ evidence / source fragments
→ coverage / issues
→ cross-product correspondence
```

without adding a second Knowledge Layer, producer, materializer, graph store, or parallel API.

## Changed runtime owners

### prepared-knowledge-runtime 0.1.0.post6

Added one typed projection registry for exact AISL item reads.

Supported representative product kinds:

- `code-declared-data-model`;
- `physical-data-model`;
- `logical-physical-model-mapping`.

The runtime reads only facts already owned by those typed schemas. Unsupported products/item kinds return an explicit unsupported projection.

### knowledge-api 0.30.9

Added the universal published-item route:

```text
GET /api/knowledge/v1/systems/{system_id}/knowledge-items/{artifact_id}/{item_kind}/{local_id}
```

Optional `revision_id` follows the existing revision-aware selection model. `artifact_id` is the published KnowledgeProduct address used as `KnowledgeItemRef.product_id`.

Added response models for exact item identity, evidence/source fragments, issues and typed correspondences. Official OpenAPI was regenerated through the package exporter.

## Deliberate non-changes

- Core unchanged.
- Runner unchanged.
- KLC unchanged.
- KCP unchanged.
- knowledge-integration unchanged in this release; generic Agent SDK tool binding is the continuation point.
- No prepared KnowledgeProduct schema was changed, so existing published DuckDB knowledge does not require rebuild for this read-boundary change.

## Evidence discipline

- resolution is not converted into Coverage;
- unsupported projection is not absence;
- correspondence is exposed only from an explicit typed mapping product;
- no reverse correspondence is guessed by name/schema similarity;
- no generic `related_to` edge is produced.
