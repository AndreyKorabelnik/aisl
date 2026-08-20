# static-analysis-runner 0.10.7

## Declarative Knowledge Product Catalog

- Removed the embedded Python `_KNOWLEDGE_POLICY` product-definition dictionary.
- Added versioned `knowledge_product_catalog/v1` as a packaged JSON resource.
- Added strict fingerprint, identity, scope, dependency and cycle validation.
- Added product-catalog provenance to compiled `knowledge_catalog/v2`.
- Added optional `knowledge-catalog --knowledge-product-catalog` for explicit catalogs.
- Removed the hidden one-to-one assumption between `knowledge_id` and `materialization_id`;
  multiple user-facing products may reference one technical materialization.
- No fallback to the removed Python policy exists.

## Compatibility

Execution semantics are unchanged. After excluding the new product-catalog provenance
fields and the Runner version bump, the compiled `knowledge_catalog/v2` is semantically
identical to the 0.10.6 baseline for the existing 16 knowledge products.
