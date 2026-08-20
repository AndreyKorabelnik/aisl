# knowledge-layer-core 0.59.15

Generalizes canonical cross-artifact physical lineage from a field-only source to explicit value origins. `logical_field` is now one origin kind alongside `storage_identity`, `reference_key`, and `object_presence`; the old `cross_artifact_logical_field_physical_lineage` table is removed rather than retained as a compatibility view.

Storage-key origins require an observed storage key field plus the existing exact storage-to-SQL mapping. `reference_key` additionally requires observed JOIN use of that key. `object_presence` additionally requires an observed existence/null-check projection along the same SQL proof path. No UCP/datamart-specific names or fuzzy correspondence rules were added.

Real Gold validation over all 27 previously proven non-field UCP origins matched the expert classification exactly: 13 storage identities, 12 reference keys and 2 object-presence values; 0 missing and 0 wrong-kind targets.
