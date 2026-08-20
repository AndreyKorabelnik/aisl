# prepared-knowledge-runtime 0.1.0.post7

- Extends the existing AISL universal exact-item read projection to the typed `persistence-lineage/v1` knowledge product.
- Addressable item kinds are the product-owned source-to-storage lineages, storage-to-access lineages, persistent writes, storage accesses, storage-lineage gaps, and stored-field-to-response-field mappings.
- Preserves the product payload and direct source evidence without inferring physical identity, business meaning, or a cross-product `maps_to` relation.
- Unresolved/candidate lineage evidence and explicit storage-lineage gaps are surfaced as item issues; item-level coverage remains `not_available` unless the typed owner publishes it.
