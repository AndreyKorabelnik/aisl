# knowledge-layer-core 0.61.0a31

- Enriches `data-model-attribute-extension-context/v1` with observed storage-reference field evidence already owned by `model-storage-semantics/v1`; no new Core analysis is introduced.
- Preserves storage API provenance, reference operation and value derivation in `basis.source_storage_field_observations` without claiming that a storage-reference field is an existing SQL column.
- Classifies every returned observed SQL JOIN example by relationship relevance (`exact_source_field_to_target_key`, related source/target cases, or labeled analogs) instead of exposing object-anchor-wide examples without qualification.
- Adds explicit diagnostics when a storage-reference field is observed but not currently observed in SQL, and when only related/analog SQL JOIN examples are available.
- Keeps confirmed structural encoding semantics confirmed while making exact-vs-analog SQL evidence visible to consumers.
